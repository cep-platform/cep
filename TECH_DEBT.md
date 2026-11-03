This is temporarily part of the repo as a todo list for cleanup


# Technical Debt & Findings

Repository audit (static analysis + test run). State at time of audit:
`uv run pytest` → **128 passed**. Coverage ~83% overall, but several modules
are unmeasured (see "Test gaps").

Findings are grouped by severity. File references use `path:line`.

> **Out of scope:** the *server-side* DNS implementation
> (`unbound/service/api.py`, `cep/server/dns.py`, and the `cep dns ...`
> commands targeting them) is slated for a full redesign, so findings
> specific to it are omitted here. Client-side DNS switching
> (`NebulaDNS` in `cep/cli/dns.py`) is a separate concern and **is** in
> scope — see §4.

---

## 1. Bugs (broken behavior today)

### 1.1 500s instead of 404s on missing resources — ✅ RESOLVED
- `src/cep/server/host.py:69` — `host delete` with an unknown network:
  `network_record` is `None` → `AttributeError` on `.hosts` → 500.
- `src/cep/server/host.py:98-100` — `_sign` does `.get()` on
  networks/hosts without checking; unknown network or host → `AttributeError`
  → 500.

> **Resolved** on `bugfix/gracefully-handle-host-server-errors`: `delete` and
> `_sign` now raise `HTTPException(404)` for unknown network/host. Regression
> tests added in `tests/test_host_endpoints.py`
> (`TestHostDelete::test_returns_404_for_unknown_network`,
> `TestSign::test_raises_404_*`, `TestSign::test_sign_endpoint_returns_404_*`).

### 1.2 `create_ca` / certificate signing are fragile — ✅ RESOLVED
- `src/cep/server/network.py:38-46` — `create_ca` runs `nebula-cert ca` in
  the *current working directory* and then globs `Path.cwd()` for `ca.*`.
  Any stale `ca.crt`/`ca.key` in the CWD gets picked up/moved, and the
  subprocess has no `check=True`, so failures are silent.
- `src/cep/server/host.py:116-125` — same pattern in `_sign`: no
  `check=True`; if signing fails, the follow-up `zipfile` write crashes with
  an unhelpful 500.

> **Resolved** on `bugfix/robust-ca-creation-and-signing`: `create_ca` now
> passes explicit `-out-crt`/`-out-key` paths inside `ca_dir` (CWD glob +
> rename removed) and raises `HTTPException(500)` with nebula-cert's stderr
> on failure. `_sign` verifies the CA files exist (500 otherwise), uses
> `check=True`, and raises `HTTPException(400)` with stderr on signing
> failure. Regression tests: `tests/test_network_helpers.py::TestCreateCa`
> (explicit output paths, stale-CWD decoys ignored, 500 on failure),
> `tests/test_network_endpoints.py::TestNetworkCreateCaFailure`
> (500 + no DB record + data dir cleaned up on failure, pre-existing dir
> untouched), `tests/test_host_endpoints.py::TestSign` (`test_raises_400_on_signing_failure`,
> `test_raises_500_when_ca_files_missing`,
> `test_sign_endpoint_returns_400_on_signing_failure`).
>
> Follow-up: the `/network/create` endpoint removes the data directory it
> just created when CA creation fails (a directory that already existed —
> duplicate-name create — is left untouched), so `/network/list`, which
> reads the data dir rather than the DB, cannot show a phantom network
> without a DB record.
>
> Follow-up (1.3): on `bugfix/network-create-post-and-409` a pre-existing
> data dir is rejected with 409 by the orphan guard before the CA step, so
> the `TestNetworkCreateCaFailure` pre-existing-dir test was superseded by
> `TestNetworkCreateDuplicate::test_returns_409_for_orphan_data_dir`.

### 1.3 Network creation has no duplicate guard — ✅ RESOLVED
- `src/cep/server/network.py:57` — creating a network whose name already
  exists silently **overwrites the DB record (wiping all hosts)** and
  regenerates the CA. Should return 409.

> **Resolved** on `bugfix/network-create-post-and-409`: `create` raises
> `HTTPException(409)` before any side effects when the name is already in
> the DB, and also when a data dir exists without a DB record (orphan).
> Regression tests: `tests/test_network_endpoints.py::TestNetworkCreateDuplicate`
> (409 preserves hosts/subnet/CA, `create_ca` never invoked, orphan dir
> rejected), plus happy-path coverage in `TestNetworkCreate`.

### 1.4 Caddy bootstrap crashes on a fresh container — ✅ RESOLVED
- `src/cep/apps/caddy.py:82-90` — Caddy's admin API returns JSON `null` for
  `GET /config` when no config is loaded. `config()` then returns `None` and
  `ensure_initialized` crashes with `AttributeError` (only `HTTPError` is
  caught). Handle the `None` case.

> **Resolved** on `bugfix/caddy-null-config-bootstrap`: `config()` normalizes
> the `null` body to `{}` (`response.json() or {}`), so `ensure_initialized`
> treats a fresh container as "no config" and installs the base config
> instead of crashing. Regression test:
> `tests/test_caddy.py::TestEnsureInitialized::test_writes_when_config_is_null`
> (the `_FakeResponse` helper previously couldn't represent a `null` body
> — its `json_data=None` default mapped to `{}`).

### 1.5 App templates are broken standalone
- `mongo.yml`, `nginx.yml`, `postgres.yml`, `python.yml`, `redis.yml`
  reference `networks: cep` but only `navidrome.yml` *defines* it
  (`external: true, name: cep_cep`). Deploying anything except navidrome
  first makes `docker compose up` fail with "undefined network".
  Every template should define the network (merge makes it idempotent).
- `nginx.yml` — `cep.proxy.port: "6969"` but stock nginx listens on 80; the
  reverse proxy target `cep-app-nginx:6969` is dead.
- `python.yml` — mounts `./app`, relative to the deployment dir; almost
  certainly not what was intended.
- `mongo.yml`/`postgres.yml` ship hardcoded weak credentials
  (`admin/password123`, `myuser/mypassword`).

### 1.6 `cep host disconnect` breaks for lighthouses and stale state
- `src/cep/cli/host.py:378-385` — in `connect --detach` the runtime file only
  gets `if_name`/`lighthouses`/`tld` for non-lighthouses. Disconnecting a
  detached lighthouse → `KeyError`. Missing/stale `runtime.json` →
  `FileNotFoundError`/`os.kill` on a dead PID. No cleanup of the file.

### 1.7 `GET /network/create` mutates state — ✅ RESOLVED
- `src/cep/server/network.py:56` (and the CLI mirrors it) — side effects
  behind GET: unsafe retries, prefetching, caching. Make it POST.

> **Resolved** on `bugfix/network-create-post-and-409`: the endpoint is now
> `POST /network/create` taking a `NetworkCreateRequest` body
> (`cep.datamodels`), mirroring the `/host/create` pattern; the CLI posts
> JSON accordingly and surfaces 409s without a traceback. Old GET callers
> receive 405.

### 1.8 Fire-and-forget compose operations
- `src/cep/apps/incus.py:129` — `compose_up` uses `subprocess.Popen` and
  never waits/checks: deploy reports success before containers exist and all
  failures are invisible.
- `src/cep/apps/incus.py:188,204` — `targeted_destroy`/`clear` are
  `async def` but block the event loop via `Popen.communicate()`; and
  `src/cep/apps/main.py:111-117` calls `compose_up()` + returns 200 even when
  the destroy return code is non-zero.

---

## 2. Security

### 2.1 Authentication is silently optional
- `src/cep/server/main.py:12` — when `CEP_SERVER_TOKEN` is unset the server
  runs **wide open with no warning**. Fail closed (or at least log a loud
  warning at startup). (The same pattern exists in the DNS service, which is
  being redesigned anyway.)
- The appstore (`src/cep/apps/main.py`) has **no auth at all** and mounts
  `/var/run/docker.sock` (documented escalation vector in AGENTS.md). Anyone
  reaching the docker network can deploy/destroy containers.
- Token comparison uses `!=`; use `secrets.compare_digest`.

### 2.2 Nebula binaries are downloaded without integrity checks
- `src/cep/utils.py:29-48` — `sha256` fields are literal `"…"` placeholders
  and `download_nebula()` never verifies anything. Supply-chain risk; pin and
  verify real hashes.
- `src/cep/utils.py:79` — `tarfile.extractall` without `filter=` (also a
  Python 3.14 deprecation warning in the test output); path-traversal risk
  with hostile archives.
- Cache invalidation: only `nebula` existence is checked — a stale/corrupt
  cache or a version bump of `NEBULA_VERSION` is never detected; a missing
  `nebula-cert` with present `nebula` crashes on `chmod`.

### 2.3 Default firewall allows everything inbound
- `src/cep/templates/config.yml` — inbound rule is `any/any/any` marked
  "For testing". Every generated host config ships wide open on the overlay.

### 2.4 Secrets handling
- `.env.example` ships `CEP_SERVER_TOKEN="aa"` as the example — encourages
  weak tokens; the unauthenticated fallback (2.1) makes this worse.
- `SignedCertificate` (`src/cep/datamodels.py:124`) includes `ca_key_path`
  (the CA *private* key). It's not zipped today, but the field has no reason
  to exist in a response model.
- `.env` is gitignored (verified) — good; keep it that way.
- `uvicorn` binds `0.0.0.0` with `reload=True` in `cep server run` /
  `cep apps run` — dev settings used by the compose deployment.

### 2.5 No TLS anywhere
- All inter-service traffic (main ↔ appstore ↔ caddy admin) is plain HTTP.
  Acceptable inside the nebula overlay long-term, but tokens then cross the
  wire in cleartext on the docker bridge network.

---

## 3. State management & consistency

- **db.json is a single JSON file with no locking and non-atomic writes** —
  ✅ RESOLVED (moved to SQLite: `src/cep/server/db.py`, WAL mode, one
  `BEGIN IMMEDIATE` transaction per mutating request via
  `get_network_store_write`)
- **Partial-failure divergence in deploy/destroy**
  (`src/cep/server/apps/__init__.py`): appstore deploy succeeds, then the
  caddy update fails → app runs but is not tracked in `network_record.apps`,
  no compensation/rollback. Same for destroy. Needs transactional steps or
  reconciliation. (Narrowed for deploy on `feature/switch-to-incus`: the
  appstore install is now an async job that cep-main polls to `done` before
  wiring caddy/DNS/DB, so the appstore leg can no longer diverge silently.)
- **Appstore install jobs are in-memory only** (`src/cep/apps/main.py`):
  `JOBS` is a process-local dict with no pruning — an appstore restart
  forgets running jobs (pollers then get 404) and finished ones. The
  deploy itself lives in incus, so only observability is lost, but a
  restart mid-deploy leaves the app deployed with nothing tracking the
  job. Persist/limit jobs once deploys outlive single-process memory.
- **`/network/list` reads the data directory, not the DB**
  (`src/cep/server/network.py:51`) — the two can diverge (dir deleted but
  record kept and vice versa). `network delete` also `rmtree`s *before*
  checking the DB (`network.py:83-95`), destroying data then 404ing.
- **`get_cep()` heuristic** (`src/cep/datamodels.py:53`) assumes the first
  host is `subnet::1` forever; deleting that host breaks app deploy/destroy
  hostname resolution. Model the "cep host" role explicitly.
- **Random host IPs are never checked for collisions**
  (`src/cep/datamodels.py:19-22,48-50`) — unlikely at /64, but free to check
  against `self.hosts`.
- **Docker deployment state vs. reality** — `list_up` trusts the compose
  file, not the daemon (the CLI even documents the inconsistency). No
  reconciliation loop.
- **Signed zip / tempdir leak** — `_sign` uses
  `TemporaryDirectory(delete=False)` and never cleans up; `FileResponse`
  serves files that accumulate in `/tmp`.

---

## 4. Code quality / maintainability

- **Dead code**: `get_apps_client` (`src/cep/cli/utils.py:52`), both
  `CEP_SERVER_CFG_PATH` definitions (with *different* values:
  `src/cep/utils.py:21` relative vs `src/cep/server/utils.py:11` home),
  `dump_state`/`read_metadata`/`verify_state` (`src/cep/apps/utils.py` —
  incl. returning the `FileNotFoundError` *class* instead of raising, and
  pickle usage).
- **Module-level side effects**: `cep/utils.py` creates dirs at import
  (documented gotcha); `cep/server/apps/__init__.py` builds an
  `httpx.Client` from env vars at import time — makes config changes and
  testing harder, and the client is never closed.
- **Proxying forwards upstream headers verbatim**
  (`Response(content=..., headers=resp.headers)` in
  `server/apps/__init__.py`) — hop-by-hop headers (`content-length`,
  `transfer-encoding`, `connection`) can corrupt the response; filter them.
- **Deprecated APIs** (visible in test warnings):
  `ComposeConfig.__fields__` (`apps/docker.py:91`) → `model_fields`;
  `tarfile.extractall` without `filter`.
- **`/debugUp` ignores its `name` parameter** (`apps/main.py:54` →
  `Docker.debug_up()` with default) — either implement per-service filtering
  or drop the parameter. Also `name` is typed required but unused.
- **Misleading naming**: `targeted_destroy(container: str)` matches on
  *service* name; `debug_up` actually lists (`docker ps`); `parse_available`
  prints "Runnig image" and uses builtin `print` (not `rich`) in
  `cli/utils.py`; `get_client` is invoked at module import in every CLI
  module, so env changes need a re-import.
- **`pyproject.toml`**: placeholder description; relies on the unmaintained
  `result` package (the comment acknowledges it — plan a migration off);
  `fastapi[standard]` pulls in `fastapi-cloud-cli`/sentry for what is a
  self-hosted tool.
- **CLI UX**: validation failures raise raw `ValueError`s with tracebacks
  (`cli/host.py:123,133`); `debug_up`'s `verbose` is an *Argument* not an
  `--option`; `cep host create` leaves half-created state on disk when the
  server call fails; `cep host delete` crashes on a missing local dir
  (`shutil.rmtree` without `ignore_errors=True`, `cli/host.py:246`).
- **macOS DNS shim** (`src/cep/cli/dns.py:86-104`): blocking `recvfrom` on
  the upstream socket (`cli/dns.py:103` — hangs the shutdown-join at 2s
  timeout), single-threaded serial proxying (drops concurrent queries), binds
  `127.0.0.1:53` (`cli/dns.py:90` — needs root and collides with
  mDNSResponder), no TCP/EDNS support, and `sock6` is never closed.
- **Linux DNS teardown is a no-op** — `_disable_linux` is `pass`
  (`src/cep/cli/dns.py:79-81`); currently works only because resolvectl
  drops the settings when the nebula interface disappears. Should explicitly
  revert `resolvectl dns/domain` (mirroring `_enable_linux`).
- **Duplicated `validate_lighthouse_ip`** in `HostRecord` and `HostRequest`
  — shared model or mixin; `serialize_ip`'s `str(ip) if ip else ip` has a
  dead branch; `deserialize_ip` accepts IPv4 for IPv6-typed fields.
- **Stale references**: `.gitignore` still lists `.cloudboxcfg`/
  `.cloudboxservercfg`; README's architecture table says cep-appstore runs on
  port 8000 (it's 8080); several `#TODO: test_this` markers remain without
  `(DONE!!)` (e.g. `server/network.py:113`, `server/host.py:31`,
  `apps/docker.py:83,98,155`, `datamodels.py:159`).
- **docker-compose**: `.env` is mounted into containers *and* passed via
  `environment:` (pick one); caddy publishes host port 8080, colliding
  conceptually with the appstore's internal 8080 (see dead `get_apps_client`).
- **Open TODOs in code worth tracking**: async app ops
  (`cli/apps/__init__.py:34,101`), store privileges enum
  (`datamodels.py:159`), O(n²) deployment merge (`apps/docker.py:89`).

---

## 5. Test gaps

Current suite: 128 tests, all passing, no live server/docker/network needed
(good). Missing or thin:

- **Unmeasured modules (0%)**: `cep/cli/host.py` (387 lines — the largest
  module), `cep/cli/dns.py` (`NebulaDNS`), `cep/cli/network.py`,
  `cep/cli/main.py`, `cep/cli/server.py`, `cep/apps/main.py`.
- **No CLI ↔ server contract tests**: the CLI builds requests by hand against
  hardcoded paths; add a round-trip test per command (CliRunner → mocked
  httpx → TestClient router) so path/verb drift gets caught.
- Would-have-caught-it tests: template validity (1.5 — lint every
  `app_templates/*.yml` for a defined `cep` network and a sane proxy port).
  (1.1's host-delete/sign 404 tests, 1.3's duplicate-create tests, and 1.4's
  null-config bootstrap test have since been added.)
- Auth behavior itself is untested: token set → 401 on bad/missing token;
  token unset → warn/refuse (2.1).
- No test exercises `uvicorn`-level serving, `connect`/`disconnect`, or the
  bundle artifact (`CepBundle.create_artifact`).

---

## 6. Suggested priority

1. **Correctness**: 1.5 (+ template lint test). (1.1, 1.3, 1.4, 1.7 done.)
2. **Security**: fail-closed auth (2.1), verify nebula downloads (2.2),
   tighten firewall default (2.3).
3. **State**: atomic/locked db writes + deploy compensation (§3).
4. **Hygiene**: dead code, deprecations, README/env cleanups, the
   client-side `NebulaDNS` fixes (§4), then the CLI test backfill (§5).
5. **Server-side DNS redesign** (owner-defined, out of scope here).
