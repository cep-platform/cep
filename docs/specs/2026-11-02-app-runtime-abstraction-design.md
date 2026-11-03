# App store: runtime abstraction (Docker → Incus)

## Why

The app store (`src/cep/apps/`) deploys apps by merging hand-written Docker
Compose templates into one shared `compose.yml` and running `docker compose up`.
We are migrating to Incus, which will replace Docker completely. Compose YAML
does not exist in Incus, but OCI images do: Incus can pull them from registries
via OCI remotes. So the stable thing to build on is "an OCI image plus a small
runtime-neutral description of how to run it", not compose.

Nothing runs in production. During the migration both runtimes must work so dev
sandboxes and workflows keep running on either.

## Goals

- Deploy **any image ref** (e.g. from Docker Hub or an Incus image server),
  not just curated templates.
- One runtime-neutral **app spec** that both runtimes consume.
- A narrow **runtime interface** with a Docker and an Incus implementation;
  everything above it (endpoints, CLI, presets) is identical for both.
- Runtime chosen **once per app-store instance** from config, so hosts can be
  migrated one at a time and Docker removed later by deleting one file and one
  branch.
- Curated catalog kept as **presets in the new spec format**.

## Non-goals

- Building images (the `ray-head` Dockerfile stays a separate build step).
- Auth, IAM, ownership or tracking which apps "belong" to whom. No state file.
  The only metadata is provenance (see *Labels*): "deployed by the app store",
  and from which preset.
- `cep/storage/` (pools/volumes) — untouched.
- ray-head. It is dead code moving to another repo: its template is not
  ported to a preset, and `apps/docker/ray-head/` is left untouched for later
  cleanup.

## Anti-goals

- A plugin system / runtime registry. There is only ever one backend per
  instance and only two total, one of which is temporary.
- Silently dropping spec fields a runtime cannot honour. Unsupported → error.
- Over-modelling: the spec only carries what current presets and ad-hoc
  deploys need.

## Design

### Layout

```
src/cep/apps/
  spec.py              AppSpec + friends, preset loading
  runtime/__init__.py  Runtime Protocol, UnsupportedSpec, get_runtime()
  runtime/docker.py    DockerRuntime
  runtime/incus.py     IncusRuntime
  presets/*.yml        catalog, in AppSpec format (replaces app_templates/)
  main.py, store.py    endpoints, now talking only to Runtime
```

`apps/docker.py`, `apps/utils.py` (only used by `docker.py`; `dump_state` etc.
are unused) and `apps/app_templates/` are deleted.

### App spec (`spec.py`)

Pydantic models:

```python
class Port(BaseModel):
    host: int
    container: int
    protocol: Literal["tcp", "udp"] = "tcp"

class Mount(BaseModel):
    source: str          # absolute path on the runtime's host, or a bare volume name;
                         # relative and ~ paths fail validation (design call)
    target: str
    read_only: bool = False

class AppSpec(BaseModel):
    name: str
    image: str                         # raw ref, interpreted by the runtime
    ports: list[Port] = []
    env: dict[str, str] = {}
    mounts: list[Mount] = []
    command: list[str] | None = None
    workdir: str | None = None
    restart: bool = True
    privileged: bool = False
    preset: str | None = None          # set by preset resolution, not by users
```

`AppStatus(name, image, state, preset)` is what `list` returns.

### Labels

Every deployed container is tagged at creation with:

- `cep.app=true` — provenance: deployed through the app store.
- `cep.preset=<name>` — only when deployed from a preset.

Docker: `--label key=value` (immutable). Incus: `-c user.cep.app=true`,
`-c user.cep.preset=<name>` (mutable, so ownership keys can be added later
without recreating containers). `list` filters on `cep.app=true`, so it only
ever shows app-store apps. Nothing else is labelled; ownership is deferred to
the IAM design.

CLI flag syntax mirrors Docker: `--port 8080:80[/udp]`, `--env K=V`,
`--volume src:target[:ro]`. Parsing those strings into `Port`/`Mount` lives in
`spec.py` so CLI and presets share it.

### Image refs

Refs follow Incus's `[remote:]image` convention. Because `:` also separates a
tag (`redis:7`), **each runtime resolves the ref** against the remotes it knows:

- **Docker**: `docker:redis:7` → `redis:7`. A bare ref (`redis:7`,
  `ghcr.io/foo/bar:1.0`) is passed to `docker` as-is. Prefixes in a fixed set
  of Incus-native remote names (`images`, `ubuntu`, `ubuntu-daily`) →
  `UnsupportedSpec`. Any other prefix is treated as part of the ref and left
  to `docker` (a bad ref then fails at run time as a 500). *(Design call.)*
- **Incus**: known remotes come from `incus remote list --format json`
  (cached at construction), including each remote's URL and protocol.
  - `remote:image` with a known remote → used as-is.
  - Bare ref whose first path segment is a registry host (contains `.` or
    `:`, e.g. `ghcr.io/foo/bar:1.0`) → pick the configured OCI remote whose URL
    host matches, strip the host. No match → `UnsupportedSpec` telling the user
    to `incus remote add <alias> https://<host> --protocol=oci`.
  - Other bare refs (`redis:7`) → the OCI remote pointing at `docker.io`.
  
  So the same fully-qualified ref works on both runtimes. Remotes are a host
  setup prerequisite documented in the apps README, never auto-added.
  *(Design call.)*

### Runtime interface (`runtime/__init__.py`)

```python
class UnsupportedSpec(ValueError): ...

class Runtime(Protocol):
    def deploy(self, spec: AppSpec) -> None: ...
    def destroy(self, name: str) -> None: ...
    def list(self) -> list[AppStatus]: ...

def get_runtime() -> Runtime:   # reads CEP_APP_RUNTIME = docker | incus (default docker)
```

Both implementations shell out to their CLI (`docker`, `incus`) via a tiny
shared helper that runs argv, raises on non-zero exit with stderr in the
message, and returns stdout. Each runtime builds its argv in **pure functions**
(spec → list of argv lists) so translation is unit-testable without a daemon.

All validation (`UnsupportedSpec`) happens before any command runs.

### Docker translation

One container per app, no compose:
`docker run -d --name <name> [-p H:C/proto] [-e K=V] [-v src:target[:ro]]
[--restart unless-stopped] [--privileged] [-w workdir] <image> [command...]`.

- `destroy`: `docker rm -f <name>`.
- `list`: `docker ps -a --filter label=cep.app=true --format json` →
  `AppStatus` (preset read from the `cep.preset` label).

### Incus translation

- `incus create <remote>:<image> <name>` with config/devices:
  - labels → `-c user.cep.app=true [-c user.cep.preset=<name>]`
  - env → `-c environment.K=V`
  - restart → `-c boot.autostart=true`
  - privileged → `-c security.privileged=true`
  - port → `incus config device add <name> port-<proto>-<host> proxy
    listen=<proto>:0.0.0.0:<host> connect=<proto>:127.0.0.1:<container>`
  - mount, absolute path → `disk source=<path> path=<target> [readonly=true]`
  - mount, bare name → custom volume in the `default` pool, created if missing
    (`incus storage volume create default <name>`), attached as
    `disk pool=default source=<name> path=<target>`
  - command / workdir → the matching OCI config keys if the installed Incus
    supports them; otherwise `UnsupportedSpec`. (Builder: verify against the
    Incus version on the dev hosts.)
- Devices are added between `incus create` and `incus start` (i.e. use
  `create` + device adds + `start` rather than `launch`) so the container never
  runs without its ports/mounts.
- `destroy`: `incus delete --force <name>`.
- `list`: `incus list user.cep.app=true --format json` → `AppStatus`.

### Presets

`presets/<name>.yml` is an `AppSpec` in YAML. Current templates are rewritten
1:1 (`mongo`, `navidrome`, `nginx`, `postgres`, `redis`, `python`); ray-head is
not ported. Presets do no env interpolation. Compose named volumes become
bare-name mounts. `python` drops its relative `./app` mount and serves its
workdir. *(Design call.)*

Fix `pyproject.toml` package-data: it currently globs `apps/app_templates/*.yaml`
but files are `.yml`; new glob is `apps/presets/*.yml`.

### API & CLI

App-store service (`apps/main.py`, `apps/store.py`):

| Endpoint | Behaviour |
|---|---|
| `POST /deploy` body `DeployRequest` | resolve → `runtime.deploy(spec)` |
| `GET /list` | `runtime.list()` |
| `DELETE /targetedDestroy?name=` | 404 unless `name` is in `runtime.list()`, else `runtime.destroy(name)` |
| `DELETE /clear` | `runtime.destroy` every app in `runtime.list()` |
| `GET /store/list` | preset names |

`DeployRequest`: `target: str` plus optional `name`, `ports`, `env`, `mounts`,
`privileged`. Resolution: if `target` is a preset name, load it; otherwise build
a spec with `image=target`. Overrides on a preset: `env` merges key-wise
(request wins); `ports` and `mounts`, if provided, replace the preset's list
wholesale (that is how you drop a clashing port); `name`/`privileged` replace.
*(Design call.)* Default
`name` = last path segment of the image without tag/remote
(`ghcr.io/foo/bar:1.0` → `bar`). Use `docker:redis` to bypass the `redis`
preset.

`UnsupportedSpec` → HTTP 422; runtime CLI failure → HTTP 500 with stderr.

Because `targetedDestroy` and `clear` only act on labelled containers, they can
never touch the app store, server, DNS or anything else on the host. Both live
in the endpoint layer, so `Runtime` stays at three methods.

`/debugUp` is removed: `list` now reports live runtime state, which is what
`debugUp` existed for.

Server proxy (`server/apps/__init__.py`) and CLI (`cli/apps/__init__.py`) are
updated to match: `deployProxy` forwards the JSON body; `debugUpProxy` is
removed. CLI:
`cep apps deploy <preset-or-image> [--name] [--port]... [--env]... [--volume]... [--privileged]`
(one target per call), `cep apps list`, `cep apps targeted-destroy <name>...`,
`cep apps clear`.

### Testing

- Pure translation tests per runtime: spec → expected argv lists, including
  labels, every `UnsupportedSpec` case and image-ref resolution.
- Endpoint tests that `targetedDestroy`/`clear` never destroy unlabelled names.
- Spec/flag parsing and preset loading (every shipped preset validates).
- Endpoint tests with a `FakeRuntime` injected via FastAPI dependency override.
- No tests require a Docker or Incus daemon.

## Left to the builder

- Making the `cep-appstore` container able to reach Incus (installing the
  `incus` client in the `Dockerfile`, mounting the Incus socket in
  `docker-compose.yml`) — or documenting running the app store on the host.
- Exact `AppStatus.state` values (pass through the runtime's own string).
- Whether `Runtime` is injected via `Depends(get_runtime)` or a module-level
  instance — `Depends` preferred for test overrides.
