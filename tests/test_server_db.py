"""
Tests for the SQLite state store (server/db.py).

Covers the transactional persistence contract:

- load_db on a fresh install -> empty store
- save_db/load_db round-trips preserve full record structure and types
- save_db overwrites (old networks disappear)
- SQLite runs in WAL mode; concurrent writers serialize on the write
  lock instead of losing updates
- get_network_store (read dependency) returns a consistent snapshot
- get_network_store_write (write dependency) persists endpoint mutations
  atomically, rolls back failed requests, and serializes concurrent
  requests so both mutations survive (regression for the lost-update
  race of the whole-file JSON save)
"""
from __future__ import annotations

import ipaddress
import sqlite3
import threading
from contextlib import contextmanager

import pytest

from cep.datamodels import AppRecord, HostRecord, NetworkRecord, NetworkStore
from cep.server import db
from cep.server.db import (
    get_network_store,
    load_db,
    save_db,
)


def store_with_records(dns: bool = False) -> NetworkStore:
    """A store exercising every field of every record type."""
    lighthouse = HostRecord(
        name="lh",
        ip=ipaddress.ip_address("fd00::1"),
        groups=["gateways", "mesh"],
        is_lighthouse=True,
        public_ip=ipaddress.ip_address("1.2.3.4"),
    )
    worker = HostRecord(
        name="worker",
        ip=ipaddress.ip_address("fd00::2"),
        groups=["workers"],
        is_lighthouse=False,
        public_key="some-pub-key",
    )
    net = NetworkRecord(
        name="mynet",
        subnet=ipaddress.IPv6Network("fd00::/64"),
        hosts={"lh": lighthouse, "worker": worker},
        apps={"redis": AppRecord(name="redis", ip=ipaddress.ip_address("fd00::99"))},
        dns=dns,
    )
    return NetworkStore(networks={"mynet": net})


class TestLoadDb:
    def test_returns_empty_store_on_fresh_install(self, server_dir):
        store = load_db()
        assert store.networks == {}
        # The db file is created empty; loading again stays stable.
        assert load_db().networks == {}

    def test_raw_rows_land_in_sqlite_after_save(self, server_dir):
        """Rows on disk, not just in memory: persistence is real."""
        save_db(store_with_records())

        conn = db.open_connection()
        try:
            assert conn.execute("SELECT COUNT(*) FROM networks").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM hosts").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0] == 1
        finally:
            conn.close()


class TestSaveDb:
    def test_creates_sqlite_db_on_first_save(self, server_dir):
        db_path = server_dir / db.DB_FILENAME
        assert not db_path.exists()

        save_db(NetworkStore(networks={}))
        assert db_path.exists()

    def test_round_trips_full_store(self, server_dir):
        save_db(store_with_records(dns=False))

        loaded = load_db()
        net = loaded.networks["mynet"]

        assert net.dns is False
        assert net.subnet == ipaddress.IPv6Network("fd00::/64")
        assert set(net.hosts) == {"lh", "worker"}
        assert set(net.apps) == {"redis"}

        lh = net.hosts["lh"]
        assert isinstance(lh.ip, ipaddress.IPv6Address)
        assert lh.is_lighthouse is True
        assert lh.public_ip == ipaddress.ip_address("1.2.3.4")
        assert lh.groups == ["gateways", "mesh"]

        worker = net.hosts["worker"]
        assert worker.is_lighthouse is False
        assert worker.public_key == "some-pub-key"

        assert net.apps["redis"].ip == ipaddress.ip_address("fd00::99")

    def test_ipv6_lighthouse_public_ip_round_trips(self, server_dir):
        net = NetworkRecord(
            name="v6net",
            subnet=ipaddress.IPv6Network("fdcc::/64"),
            hosts={
                "lh": HostRecord(
                    name="lh",
                    ip=ipaddress.ip_address("fdcc::1"),
                    groups=[],
                    is_lighthouse=True,
                    public_ip=ipaddress.ip_address("fdff::10"),
                )
            },
            dns=False,
        )
        save_db(NetworkStore(networks={"v6net": net}))

        reloaded = load_db()
        assert reloaded.networks["v6net"].hosts["lh"].public_ip == ipaddress.ip_address("fdff::10")

    def test_overwrite_removes_old_networks(self, server_dir):
        net_a = NetworkRecord(name="a", subnet="fda0::/64", hosts={}, dns=False)
        net_b = NetworkRecord(name="b", subnet="fdb0::/64", hosts={}, dns=True)

        save_db(NetworkStore(networks={"a": net_a}))
        save_db(NetworkStore(networks={"b": net_b}))

        final = load_db()
        assert "a" not in final.networks
        assert "b" in final.networks
        assert final.networks["b"].dns is True

    def test_opens_again_under_wal_journal_mode(self, server_dir):
        save_db(NetworkStore(networks={}))
        conn = sqlite3.connect(server_dir / db.DB_FILENAME)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        assert mode == "wal"


class TestGetNetworkStore:
    """The read-only FastAPI dependency."""

    def test_returns_empty_store_when_fresh(self, server_dir):
        assert get_network_store().networks == {}

    def test_returns_current_store_contents(self, server_dir):
        save_db(store_with_records(dns=True))

        store = get_network_store()

        assert "mynet" in store.networks
        assert store.networks["mynet"].dns is True
        assert "lh" in store.networks["mynet"].hosts


class TestWriteLocking:
    def test_second_immediate_writer_blocks_on_busy_timeout(self, server_dir):
        a = db.open_connection()
        try:
            a.execute("BEGIN IMMEDIATE")

            b = db.open_connection(timeout=0.2)
            try:
                with pytest.raises(sqlite3.OperationalError, match="database is locked"):
                    b.execute("BEGIN IMMEDIATE")

                # Once the lock holder commits, the waiting writer proceeds.
                a.commit()
                b.execute("BEGIN IMMEDIATE")  # would raise if a still held the lock
            finally:
                b.close()
        finally:
            a.close()

    def test_concurrent_write_dependencies_both_persist(self, server_dir):
        """
        Regression for the lost-update race: two concurrent requests each add
        a host to a different network. Both must survive, because each write
        dependency loads the store inside BEGIN IMMEDIATE and commits before
        the other's load can start.
        """
        save_db(store_with_records())
        host_ips = {"extra1": "fd00::10", "extra2": "fd00::11"}
        errors: list[BaseException] = []

        def add_host(host_name: str) -> None:
            try:
                with contextmanager(db.get_network_store_write)() as store:
                    net = store.networks["mynet"]
                    net.hosts[host_name] = HostRecord(
                        name=host_name,
                        ip=ipaddress.ip_address(host_ips[host_name]),
                        groups=[],
                        is_lighthouse=False,
                    )
            except BaseException as e:  # pragma: no cover - failure diagnostics
                errors.append(e)

        threads = [
            threading.Thread(target=add_host, args=(name,)) for name in host_ips
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        final = load_db()
        assert set(final.networks["mynet"].hosts) == {"lh", "worker", *host_ips}


class TestPoolAndGuardrails:
    """Connection pooling helpers and defensive paths."""

    def test_invalid_sync_mode_is_rejected(self, server_dir, monkeypatch):
        monkeypatch.setenv("CEP_SQLITE_SYNC", "VERYFAST")
        with pytest.raises(ValueError, match="CEP_SQLITE_SYNC"):
            db.acquire_connection()

    def test_pooled_connection_is_reused(self, server_dir):
        first = db.acquire_connection()
        db.release_connection(first)
        assert db.acquire_connection() is first
        db.release_connection(first)

    def test_second_borrower_gets_a_new_connection(self, server_dir):
        first = db.acquire_connection()
        second = db.acquire_connection()
        assert second is not first
        db.release_connection(first)
        db.release_connection(second)

    def test_stale_path_connection_is_not_reused(self, server_dir, monkeypatch):
        stale = db.acquire_connection()
        db.release_connection(stale)  # pooled under the current test's path

        new_dir = server_dir.parent / "server_alt"
        new_dir.mkdir()
        monkeypatch.setattr("cep.server.utils.SERVER_DATA_DIR", new_dir)

        fresh = db.acquire_connection()
        assert fresh is not stale
        db.release_connection(fresh)

    def test_releasing_after_repoining_closes_stale_connection(self, server_dir, monkeypatch):
        conn = db.acquire_connection()

        new_dir = server_dir.parent / "server_alt"
        monkeypatch.setattr("cep.server.utils.SERVER_DATA_DIR", new_dir)

        db.release_connection(conn)  # stale path: must be closed, not pooled

        new_dir.mkdir()
        fresh = db.acquire_connection()
        assert fresh is not conn
        db.release_connection(fresh)

    def test_releasing_dirty_connection_rolls_back_first(self, server_dir):
        conn = db.acquire_connection()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO networks(name, subnet, dns) VALUES('dirty', 'fd00::/64', 0)"
        )

        db.release_connection(conn)

        assert not conn.in_transaction
        follow = db.acquire_connection()
        try:
            assert (
                follow.execute(
                    "SELECT COUNT(*) FROM networks WHERE name = 'dirty'"
                ).fetchone()[0]
                == 0
            )
        finally:
            db.release_connection(follow)

    def test_write_transaction_rolls_back_on_exception(self, server_dir):
        with pytest.raises(RuntimeError, match="boom"):
            with db.write_transaction() as conn:
                conn.execute(
                    "INSERT INTO networks(name, subnet, dns) VALUES('x', 'fd00::/64', 0)"
                )
                raise RuntimeError("boom")

        assert "x" not in load_db().networks


class TestWriteDependencyEndpoints:
    """End-to-end: mutating endpoints persist through the write dependency."""

    def test_network_create_persists(self, api, server_dir):
        response = api.post("/network/create", json={"name": "newnet", "dns": False})
        assert response.status_code == 200

        store = load_db()
        assert "newnet" in store.networks
        assert (server_dir / "newnet").is_dir()

    def test_network_create_duplicate_idempotent(self, api, server_dir):
        assert api.post("/network/create", json={"name": "newnet", "dns": False}).status_code == 200
        response = api.post("/network/create", json={"name": "newnet", "dns": False})
        assert response.status_code == 409

        store = load_db()
        assert list(store.networks) == ["newnet"]

    def test_failed_request_rolls_back(self, api, server_dir, monkeypatch):
        """A request that fails after mutating in memory must leave no trace."""
        def _exploding_start_dns(**kwargs):
            raise RuntimeError("dns service down")

        monkeypatch.setattr("cep.server.network.start_dns", _exploding_start_dns)

        with pytest.raises(RuntimeError):
            api.post("/network/create", json={"name": "doomed", "dns": True})

        assert load_db().networks == {}

    def test_host_create_persists_and_delete_persists(self, api, server_dir, mock_dns):
        seed_ok = api.post("/network/create", json={"name": "newnet", "dns": False})
        assert seed_ok.status_code == 200

        create = api.post(
            "/host/create",
            json={
                "name": "h1",
                "network_name": "newnet",
                "is_lighthouse": False,
            },
        )
        assert create.status_code == 200

        store = load_db()
        expected_first_host = next(store.networks["newnet"].subnet.hosts())
        assert "h1" in store.networks["newnet"].hosts
        assert store.networks["newnet"].hosts["h1"].ip == expected_first_host

        delete = api.delete("/host/delete", params={"network_name": "newnet", "host_name": "h1"})
        assert delete.status_code == 200
        assert "h1" not in load_db().networks["newnet"].hosts

    def test_concurrent_api_host_creates_both_persist(self, api, server_dir, mock_dns):
        """The end-to-end lost-update regression via real HTTP requests."""
        for net in ("n1", "n2"):
            assert api.post("/network/create", json={"name": net, "dns": False}).status_code == 200

        responses: list = []
        errors: list[BaseException] = []

        def create_host(net: str, host: str) -> None:
            try:
                responses.append(
                    api.post(
                        "/host/create",
                        json={"name": host, "network_name": net, "is_lighthouse": False},
                    )
                )
            except BaseException as e:  # pragma: no cover - failure diagnostics
                errors.append(e)

        threads = [
            threading.Thread(target=create_host, args=("n1", "h1")),
            threading.Thread(target=create_host, args=("n2", "h2")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert all(r.status_code == 200 for r in responses)

        store = load_db()
        assert "h1" in store.networks["n1"].hosts
        assert "h2" in store.networks["n2"].hosts