"""SQLite-backed persistence for cep-main's state.

The server keeps its state (networks, hosts, apps) in a single SQLite
file (WAL mode) in the user data dir. Whole-store load/persist runs
inside transactions, so concurrent requests serialize on the database
lock instead of racing (TECH_DEBT 3).

Design notes:

- WAL mode + ``BEGIN IMMEDIATE`` write transactions. Each mutating
  request loads the store inside a write transaction held for the whole
  request (``get_network_store_write``), so read-modify-write cycles
  serialize on the database lock instead of racing. Plain readers never
  block (WAL snapshot reads).
- Zero new infrastructure: the DB is a file next to the network data
  dirs. No new compose service, no credentials, no network surface.
- The in-memory Pydantic models stay the API surface: routers get a
  ``NetworkStore`` and edit it in place. SQLite is an implementation
  detail behind ``load_db``/``save_db`` and the two FastAPI dependencies.
- The schema is a 1:1 mapping of the current nested-dict models and
  persisting is a whole-store replace inside one transaction (row counts
  are tiny). Refactoring into junction tables for the upcoming
  many-to-many relations (apps ↔ networks, hosts ↔ networks) is
  deliberately deferred until the data model itself is reworked.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cep.datamodels import AppRecord, HostRecord, NetworkRecord, NetworkStore

DB_FILENAME = "db.sqlite3"
# How long a writer waits for the write lock before raising
# sqlite3.OperationalError("database is locked").
_BUSY_TIMEOUT_S = 5.0
# Warm connections kept between requests. Bounds how many idle conns may
# linger; excess or stale ones get closed on release.
_POOL_MAX = 8
_VALID_SYNC_MODES = ("OFF", "NORMAL", "FULL", "EXTRA")


def _sync_mode() -> str:
    """
    Resolve the SQLite `synchronous` pragma from CEP_SQLITE_SYNC
    (default NORMAL). See AGENTS.md's environment variable table.
    """
    mode = os.environ.get("CEP_SQLITE_SYNC", "NORMAL").upper()
    if mode not in _VALID_SYNC_MODES:
        raise ValueError(
            f"CEP_SQLITE_SYNC must be one of {_VALID_SYNC_MODES}, got {mode!r}"
        )
    return mode


SCHEMA = """
CREATE TABLE IF NOT EXISTS networks (
    name TEXT PRIMARY KEY,
    subnet TEXT NOT NULL,
    dns INTEGER NOT NULL DEFAULT 0
           );
CREATE TABLE IF NOT EXISTS hosts (
    network_name TEXT NOT NULL REFERENCES networks(name) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    -- "groups" is a SQLite keyword, hence the *_json suffix
    groups_json TEXT NOT NULL DEFAULT '[]',
    is_lighthouse INTEGER NOT NULL DEFAULT 0,
    public_key TEXT,
    public_ip TEXT,
    PRIMARY KEY (network_name, name)
           );
CREATE TABLE IF NOT EXISTS apps (
    network_name TEXT NOT NULL REFERENCES networks(name) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    PRIMARY KEY (network_name, name)
           );
"""


#TODO: test_this (DONE!!): identify existing and non existing dbs across all entry points
def _server_data_dir() -> Path:
    """
    Resolve the server data dir lazily, never at import time.

    Tests redirect state into tmp dirs by monkeypatching the module-level
    ``SERVER_DATA_DIR`` attribute (see tests/conftest.py), so db.py must
    look it up at call time rather than binding it at import.
    """
    from cep.server.utils import SERVER_DATA_DIR

    return SERVER_DATA_DIR


def _db_path() -> Path:
    return _server_data_dir() / DB_FILENAME


def open_connection(
    path: Path | None = None,
    *,
    timeout: float = _BUSY_TIMEOUT_S,
) -> sqlite3.Connection:
    """
    Open a *fresh*, unpooled connection to the state DB with cep's pragmas
    and schema applied. For request handling prefer acquire_connection/
    release_connection so connections are reused (see below).

    - ``journal_mode=WAL``: concurrent readers + a single serialized
      writer; persistent in the file, re-asserted for fresh DBs.
    - ``foreign_keys=ON``: per-connection; makes hosts/apps cascade when a
      network row is deleted.
    - ``synchronous``: from the CEP_SQLITE_SYNC env var, default
      ``NORMAL`` — the recommended WAL pairing; commits stay in the WAL
      (no per-commit fsync), durability is settled at checkpoints.
      Crash-safe, single-node appropriate.
    - ``check_same_thread=False``: connections are used sequentially by
      FastAPI threadpool threads, one user at a time, never by two
      threads concurrently.
    - ``isolation_level=None``: transactions are managed explicitly via
      BEGIN IMMEDIATE/COMMIT, not implicitly by the sqlite3 module.

    ``timeout`` maps to SQLite's busy handler: how long a lock-seeked
    writer waits before raising OperationalError("database is locked").
    """
    return _new_connection(path or _db_path(), timeout)


class _Connection(sqlite3.Connection):
    """Connection subclass: gives instances a __dict__ so pooled conns can
    carry the db path they were opened for (stale-path detection)."""


def _new_connection(path: Path, timeout: float) -> sqlite3.Connection:
    conn = sqlite3.connect(
        path,
        timeout=timeout,
        check_same_thread=False,
        isolation_level=None,
        factory=_Connection,
    )
    conn.row_factory = sqlite3.Row
    conn.cep_db_path = path
    # Order matters: a brand-new db is synchronous=FULL by default, so set
    # `synchronous` BEFORE switching to WAL — the journal-mode conversion
    # of a fresh file fsyncs under the then-current sync level (which on
    # slow-fsync filesystems costs the whole request dearly).
    conn.execute(f"PRAGMA synchronous={_sync_mode()}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


_pool_lock = threading.Lock()
_pool: list[sqlite3.Connection] = []


def acquire_connection(timeout: float = _BUSY_TIMEOUT_S) -> sqlite3.Connection:
    """
    Borrow a connection for a single unit of work; release when done.

    Connections are pooled and reused across requests on purpose:
    closing the *last* connection to a WAL database runs a checkpoint
    (a couple of fsyncs), so churning one connection per request put
    that on every request's critical path. Keeping warm connections
    avoids it: commits stay cheap and WAL sweeping happens via
    SQLite's lazy autocheckpoint (every 1000 pages) instead of
    close-time checkpoints.

    Pooled connections for a stale path (tests redirect SERVER_DATA_DIR
    between tests) are closed on the way out.
    """
    path = _db_path()
    with _pool_lock:
        while _pool:
            conn = _pool.pop()
            if getattr(conn, "cep_db_path", None) == path:
                return conn
            _close_quietly(conn)
    return _new_connection(path, timeout)


def release_connection(conn: sqlite3.Connection) -> None:
    """Return a healthy idle connection to the pool; else close it."""
    if conn.in_transaction:
        try:
            conn.rollback()
        except sqlite3.ProgrammingError:  # pragma: no cover - already closed
            return
    with _pool_lock:
        if getattr(conn, "cep_db_path", None) == _db_path() and len(_pool) < _POOL_MAX:
            _pool.append(conn)
            return
    _close_quietly(conn)


def _close_quietly(conn: sqlite3.Connection) -> None:
    try:
        conn.close()
    except sqlite3.Error:  # pragma: no cover - best effort cleanup
        pass


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _load_store(conn: sqlite3.Connection) -> NetworkStore:
    """Rebuild the in-memory network store from the database."""
    networks: dict[str, NetworkRecord] = {}
    for row in conn.execute("SELECT name, subnet, dns FROM networks"):
        networks[row["name"]] = NetworkRecord(
            name=row["name"],
            subnet=row["subnet"],
            hosts={},
            apps={},
            dns=bool(row["dns"]),
        )
    for row in conn.execute(
        "SELECT network_name, name, ip, groups_json, is_lighthouse, "
        "public_key, public_ip FROM hosts"
    ):
        network = networks[row["network_name"]]
        network.hosts[row["name"]] = HostRecord(
            name=row["name"],
            ip=row["ip"],
            groups=json.loads(row["groups_json"]),
            is_lighthouse=bool(row["is_lighthouse"]),
            public_key=row["public_key"],
            public_ip=row["public_ip"],
        )
    for row in conn.execute("SELECT network_name, name, ip FROM apps"):
        network = networks[row["network_name"]]
        network.apps[row["name"]] = AppRecord(name=row["name"], ip=row["ip"])
    return NetworkStore(networks=networks)


def _persist_store(conn: sqlite3.Connection, store: NetworkStore) -> None:
    """
    Whole-store replace inside the caller's open transaction:
    correctness and simplicity over diffing (datasets are tiny). Children
    delete via cascade.
    """
    conn.execute("DELETE FROM apps")
    conn.execute("DELETE FROM hosts")
    conn.execute("DELETE FROM networks")
    for network in store.networks.values():
        conn.execute(
            "INSERT INTO networks(name, subnet, dns) VALUES (?, ?, ?)",
            (network.name, str(network.subnet), int(network.dns)),
        )
        for host in network.hosts.values():
            conn.execute(
                "INSERT INTO hosts("
                "network_name, name, ip, groups_json, is_lighthouse, "
                "public_key, public_ip) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    network.name,
                    host.name,
                    str(host.ip),
                    json.dumps(host.groups),
                    int(host.is_lighthouse),
                    host.public_key,
                    str(host.public_ip) if host.public_ip is not None else None,
                ),
            )
        for app in network.apps.values():
            conn.execute(
                "INSERT INTO apps(network_name, name, ip) VALUES (?, ?, ?)",
                (network.name, app.name, str(app.ip)),
            )


@contextmanager
def write_transaction() -> Iterator[sqlite3.Connection]:
    """
    Unit of work: BEGIN IMMEDIATE .. COMMIT/ROLLBACK around the body.

    BEGIN IMMEDIATE grabs the write lock up front, so nothing read by the
    body can be changed by another writer before commit. Concurrent
    writers arriving while the lock is held wait up to the busy timeout
    and then raise sqlite3.OperationalError("database is locked").
    """
    conn = acquire_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        release_connection(conn)


#TODO: test_this (DONE!!): existing and non existing dbs
def load_db() -> NetworkStore:
    """Load a consistent snapshot of the store from the database."""
    conn = acquire_connection()
    try:
        conn.execute("BEGIN")  # deferred read tx: one snapshot across tables
        try:
            return _load_store(conn)
        finally:
            conn.rollback()  # read-only snapshot, nothing to persist
    finally:
        release_connection(conn)


#TODO: test_this (DONE!!): existing and non existing dbs
def save_db(store: NetworkStore) -> None:
    """
    Persist the whole store in a single atomic transaction.

    For endpoints, prefer ``get_network_store_write``: it loads and saves
    inside one held transaction, so concurrent requests cannot interleave
    between the two. A bare load_db()/save_db() pair is atomic per call,
    not across the pair.
    """
    with write_transaction() as conn:
        _persist_store(conn, store)


def get_network_store() -> NetworkStore:
    """
    FastAPI dependency for read-only endpoints: a consistent snapshot.

    Reads run in a WAL snapshot transaction; readers never block writers
    and writers never block readers.
    """
    return load_db()


def get_network_store_write() -> Iterator[NetworkStore]:
    """
    FastAPI dependency for mutating endpoints: transaction per request.

    The store is loaded inside a BEGIN IMMEDIATE transaction held for the
    whole request. Endpoints mutate the model tree in place; on success
    the tree is persisted and the transaction committed. Any exception
    (including HTTPException) rolls back, so no half-finished mutations
    survive a failed request.

    This is what closes the read-modify-write race of the old JSON store:
    load and persist now share one transaction, so concurrent requests
    genuinely serialize instead of last-writer-wins on a whole file.
    """
    conn = acquire_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            store = _load_store(conn)
            yield store
        except BaseException:
            conn.rollback()
            raise
        else:
            _persist_store(conn, store)
            conn.commit()
    finally:
        release_connection(conn)