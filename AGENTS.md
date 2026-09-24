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

Docker deployment (only needed when working on deployment itself):

```bash
cp .env.example .env         # then set LIGHTHOUSE_STABLE_IP
docker build . -t cep:latest
docker compose up -d
```

No linter/formatter is configured yet — if you add one, document it here.

## Repository layout

```
src/cep/
  cli/           Typer CLI. main.py registers sub-apps: network, host,
                 server, dns, apps, storage. New commands: own module +
                 register in cli/main.py.
  server/        cep-main FastAPI app. main.py builds app with bearer-token
                 auth; routers: network, host, apps, dns, storage.
                 Persistence is a JSON file (db.json) in the user data dir.
  apps/          cep-appstore FastAPI app (Docker deploy + store router).
  storage/       Storage abstraction: Pool / Volume over Docker.
  datamodels.py  Shared Pydantic models (NetworkRecord, HostRecord, ...).
                 Validators/serializers keep ipaddress types JSON-safe.
  utils.py       Nebula binary download/cache (~/.cache/nebula), platform
                 detection, template lookup, stdout parsing.
  templates/     Packaged YAML/JSON templates (nebula config, bundle).
tests/           Pytest suite (see Testing rules).
unbound/         cep-dns: unbound config + FastAPI control API.
startupscripts/  Client container entrypoints.
```

## Testing rules

- Tests must run without a live server, Docker daemon, network access, or
  nebula binaries — mock HTTP (TestClient), subprocesses, and DNS calls.
- Shared fixtures live in `tests/conftest.py` (`server_dir` isolates
  SERVER_DATA_DIR/DB_PATH to a tmp dir; `mock_dns`; `mock_create_ca`;
  TestClient + CliRunner). Reuse them instead of re-patching globals;
  extend conftest for new shared state.
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
| CEP_STORAGE_PATH     | appstore           | Bind-mount for storage   |

## Gotchas

- `src/cep/utils.py` creates DATA_DIR/CACHE_DIR at import time — never
  patch those globals in tests; monkeypatch module-level paths like
  conftest.py does.
- `APP_TEMPLATE_PATH` (utils.py) points to `src/cep/app_templates/`,
  which does not exist in the repo; prefer `get_template_path()`
  (importlib.resources on `cep.templates`) and `cep.apps.app_templates`.
- The appstore mounts `/var/run/docker.sock` — a known privilege
  escalation vector; never expose it beyond the compose file.
- The README's "Test structure" table is stale; trust `tests/` files.
- Nebula binaries are pre-downloaded at Docker build time; don't add
  runtime downloads outside `download_nebula()`.

## Git conventions

- Branches: `<type>/<kebab-case>` with type in {feature, bugfix, chore,
  docs} (e.g. `feature/attach-volume`).
- Small focused PRs; include tests for behavior changes.