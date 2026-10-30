# AGENTS.md

Guidance for AI coding agents working on this repository.

## What is Cep?

Cep is a self-hosted platform for securely deploying web apps. It manages
[Nebula](https://github.com/slackhq/nebula) peer-to-peer VPN networks and
deploys Docker containers via an app store. Long-term goals live in
`REQUIREMENTS.md`; we are in Phase 1 (MVP): OCI containers + Compose-like
abstraction, Nebula networking, simple AppSpec, single-node federation.

## Components

| Component    | Port | Location                   |
|--------------|------|----------------------------|
| cep-main     | 8000 | `src/cep/server/` (FastAPI) |
| cep-appstore | 8000 | `src/cep/apps/` (FastAPI)   |
| cep-client   | —    | `src/cep/cli/` (Typer CLI)  |
| cep-dns      | 8053 | `unbound/service/api.py`    |

## Commands

Package management is [uv](https://docs.astral.sh/uv/), Python >= 3.13.

```bash
uv sync --group dev          # install deps incl. pytest/pytest-cov
uv pip install -e .          # editable install of cep

uv run pytest                # run the full test suite (always do this before finishing)
uv run pytest --cov=cep --cov-report=term-missing
uv run pytest tests/test_network_endpoints.py

uv run cep --help            # CLI smoke test
```

Incus deployment (only needed when working on deployment itself):

```bash
cp .env.example .env         # then set LIGHTHOUSE_STABLE_IP
./image/build.sh             # build the nix OCI image, import into the
                              # incus-compose image cache (local/cep:latest,
                              # local/cep:latest/amd64)
make deploy                  # incus-compose up (stack) + host-side dev extras
make dev                     # same as deploy, but with the live-reload
                              # overlay (compose.dev.yml: ./src bind-mounted,
                              # PYTHONPATH overrides the baked package)
```

No linter/formatter is configured yet — if you add one, document it here.

## Repository layout

```
src/cep/
  cli/           Typer CLI. main.py registers sub-apps: network, host,
                 server, dns, apps. New commands: own module +
                 register in cli/main.py.
  server/        cep-main FastAPI app. main.py builds app with bearer-token
                 auth; routers: network, host, apps, dns.
                 Persistence is SQLite (db.sqlite3, WAL) in the user data
                 dir; owned by server/db.py: mutating endpoints run in a
                 BEGIN IMMEDIATE transaction per request via
                 get_network_store_write, read endpoints snapshot via
                 get_network_store.
  apps/          cep-appstore FastAPI app (incus deploy via incus-compose
                 + store router; shells out to incus/incus-compose inside the
                 appstore container, talking to the host daemon via a
                 trust-token remote, scripts/register-appstore-client.sh).
  datamodels.py  Shared Pydantic models (NetworkRecord, HostRecord, ...).
                 Validators/serializers keep ipaddress types JSON-safe.
  utils.py       Nebula binary download/cache (~/.cache/nebula), platform
                 detection, template lookup, stdout parsing.
  templates/     Packaged YAML/JSON templates (nebula config, bundle).
image/           OCI image flake: image.nix (nix2container image, Entrypoint
                 = cep), flake.nix, build.sh (build + import into the
                 incus-compose cache), incusify.py (OCI layout -> incus
                 split tarballs).
nix/             NixOS host flake (nixosConfigurations.incus: incus preseed,
                 core.https_address :8443, firewall). Rebuild with
                 `nixos-rebuild switch --flake ./nix#incus --impure`.
tests/           Pytest suite (see Testing rules).
unbound/         cep-dns: unbound config + FastAPI control API.
startupscripts/  Client container entrypoints.
```

## Testing rules

- Tests must run without a live server, Docker daemon, network access, or
  nebula binaries — mock HTTP (TestClient), subprocesses, and DNS calls.
- Shared fixtures live in `tests/conftest.py` (`server_dir` isolates
  SERVER_DATA_DIR to a tmp dir and sets CEP_SQLITE_SYNC=OFF;
  `mock_dns`; `mock_create_ca`; TestClient + CliRunner). Reuse them
  instead of re-patching globals; extend conftest for new shared state.
- Server tests run token-free: `CEP_SERVER_TOKEN` must not leak into the
  test environment.
- Behavior changes need tests in the matching test file.

## Code conventions

- Python 3.13+, Pydantic v2, FastAPI, Typer, `result` (Ok/Err).
- Start modules with `from __future__ import annotations`.
- Domain types live in `src/cep/datamodels.py` — extend Pydantic models
  with validators/serializers rather than passing ad-hoc dicts.
- TODO markers: `#TODO: <what>` and append `(DONE!!)` when resolved.
- User-facing CLI output uses `rich`; errors must be actionable.
- Never log or print tokens (CEP_SERVER_TOKEN, DNS_TOKEN).

## Environment variables

| Variable             | Used by            | Purpose                  |
|----------------------|--------------------|--------------------------|
| CEP_SERVER_TOKEN     | main server/client | Bearer token auth        |
| CEP_SERVER_URL       | client             | URL of cep-main          |
| DNS_TOKEN            | main / dns         | DNS API auth             |
| LIGHTHOUSE_STABLE_IP | client / server    | Public IP of lighthouse  |
| DNS_IP               | main               | DNS server IP            |
| CEP_SQLITE_SYNC      | main               | SQLite `synchronous` pragma
                                          (OFF/NORMAL/FULL, default NORMAL;
                                          the WAL conversion of a fresh db
                                          fsyncs once, so keep the order in
                                          `db._new_connection()` if touched) |

## Gotchas

- `src/cep/utils.py` creates DATA_DIR/CACHE_DIR at import time — never
  patch those globals in tests; monkeypatch module-level paths like
  conftest.py does.
- `src/cep/server/db.py` resolves the sqlite path from
  `cep.server.utils.SERVER_DATA_DIR` **at call time** (not import time) so
  the conftest monkeypatch works; keep that lazy resolution. Connections
  are pooled — always pair `acquire_connection` with `release_connection`.
- `PRAGMA synchronous` must be set **before** `PRAGMA journal_mode=WAL`
  in `db._new_connection()`: switching a fresh db to WAL fsyncs under the
  then-current sync level.
- App templates live in `src/cep/apps/app_templates/` and are looked up
  via importlib.resources as `cep.apps.app_templates` (see
  `cep.apps.incus`); nebula/bundle templates live in `src/cep/templates/`
  (`get_template_path()`).
- Image build: `image/build.sh` imports the nix-built image under
  `local/cep:latest` AND `local/cep:latest/amd64` in the
  `incus-compose-cache` project — incus-compose looks images up with the
  platform suffix (`cacheAlias()`); a plain `local/cep:latest` alias alone
  is never found. incus rejects duplicate fingerprints, so build.sh deletes
  the previous import first.
- The image flake uses `src = self` (the tracked git tree): `git add` new
  files before `nix build`, or the build won't see them.
- The appstore deploys arbitrary app templates through the host incus
  daemon (own client cert + trust token,
  `scripts/register-appstore-client.sh`) — the same privilege-escalation
  surface class as a docker.sock mount; never widen the appstore's daemon
  access beyond that registration.
- Nebula binaries are baked into the image at build time (symlinked into
  `~/.cache/nebula`, see `image/image.nix`); don't add runtime downloads
  outside `download_nebula()`.

## Git conventions

- Branches: `<type>/<kebab-case>` with type in {feature, bugfix, chore,
  docs} (e.g. `feature/attach-volume`).
- Small focused PRs; include tests for behavior changes.
