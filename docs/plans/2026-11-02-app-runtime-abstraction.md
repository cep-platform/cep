# App Runtime Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the compose-template app store with a runtime-neutral `AppSpec` deployed through a three-method `Runtime` interface that has Docker and Incus implementations.

**Architecture:** `cep/apps/spec.py` owns the models, flag parsing, presets and request resolution. `cep/apps/runtime/` holds the `Runtime` Protocol plus `DockerRuntime` and `IncusRuntime`, which shell out to their CLIs; all argv construction is pure and unit-tested. Endpoints depend on `Runtime` via `Depends(get_runtime)`; the server proxy and CLI forward to them.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Typer, PyYAML, pytest (`uv run pytest`).

**Spec:** `docs/superpowers/specs/2026-11-02-app-runtime-abstraction-design.md`

## Global Constraints

- Runtime selected by env var `CEP_APP_RUNTIME` = `docker` | `incus`, default `docker`.
- Labels: `cep.app=true` always; `cep.preset=<name>` only when deployed from a preset. Docker: `--label`. Incus: `user.cep.app`, `user.cep.preset` config keys.
- `list`, `targetedDestroy` and `clear` only ever see/act on containers labelled `cep.app=true`.
- Spec-level problems (`InvalidSpec`, incl. `UnsupportedSpec`) → HTTP 422, raised before any runtime command runs. Runtime CLI failure (`CommandFailed`) → HTTP 500 with stderr.
- No tests may require a Docker or Incus daemon.
- `Runtime` has exactly three methods: `deploy`, `destroy`, `list`.
- Don't touch `cep/storage/`, `apps/docker/ray-head/`, or the storage endpoints in `apps/main.py`.

## Review Focus

1. **Deploy name collides with an existing container** → runtime CLI error surfaces as a 500 with Docker/Incus's own "already in use/exists" stderr, not a hang or a half-created app. (Task 5 test.)
2. **Incus deploy fails mid-way** (e.g. port already bound on `device add`) → the half-created instance is deleted, so a retry with the same name works. (Task 5 test.)
3. **Ref with no derivable valid name** (`images:debian/12`, `UPPER:1`) and no `--name` → 422 telling the user to pass a name, not a runtime error. (Task 2 test.)
4. **`targetedDestroy` on a name that exists on the host but isn't an app** (e.g. `cep-appstore`) → 404, nothing destroyed. (Task 6 test.)
5. **Preset override with `--env` only** keeps the preset's other env vars and its ports/mounts untouched. (Task 2 test.)

---

### Task 1: Spec models and flag parsing

**Files:**
- Create: `src/cep/apps/spec.py`
- Test: `tests/test_apps_spec.py`

**Interfaces:**
- Produces (all in `cep.apps.spec`):
  - `class InvalidSpec(ValueError)`
  - `Port(host: int, container: int, protocol: Literal["tcp","udp"]="tcp")`
  - `Mount(source: str, target: str, read_only: bool=False)`; property `is_volume: bool` (source is a bare name)
  - `AppSpec(name, image, ports=[], env={}, mounts=[], command: list[str]|None=None, workdir: str|None=None, restart=True, privileged=False, preset: str|None=None)`
  - `AppStatus(name: str, image: str, state: str, preset: str|None=None)`
  - `parse_port(s: str) -> Port`, `parse_mount(s: str) -> Mount`, `parse_env(s: str) -> tuple[str, str]` — all raise `InvalidSpec` on bad input
  - `NAME_RE = r"^[a-z][a-z0-9-]{0,62}$"`, `INCUS_NATIVE_REMOTES = frozenset({"images", "ubuntu", "ubuntu-daily"})`, `KNOWN_REMOTE_PREFIXES = INCUS_NATIVE_REMOTES | {"docker"}`

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_port():
    assert parse_port("8080:80") == Port(host=8080, container=80, protocol="tcp")
    assert parse_port("53:53/udp") == Port(host=53, container=53, protocol="udp")

@pytest.mark.parametrize("bad", ["80", "a:b", "1:2/sctp", ""])
def test_parse_port_rejects(bad):
    with pytest.raises(InvalidSpec): parse_port(bad)

def test_parse_mount():
    assert parse_mount("/srv/x:/data") == Mount(source="/srv/x", target="/data")
    assert parse_mount("pgdata:/var/lib/pg:ro") == Mount(source="pgdata", target="/var/lib/pg", read_only=True)
    assert parse_mount("pgdata:/x").is_volume and not parse_mount("/a:/x").is_volume

@pytest.mark.parametrize("bad", ["./app:/app", "~/x:/x", "a/b:/x", "/a", "/a:/b:rw"])
def test_parse_mount_rejects(bad):
    with pytest.raises(InvalidSpec): parse_mount(bad)

def test_parse_env():
    assert parse_env("K=a=b") == ("K", "a=b")
    with pytest.raises(InvalidSpec): parse_env("novalue")

@pytest.mark.parametrize("bad", ["Redis", "1abc", "my_app", ""])
def test_appspec_rejects_bad_names(bad):
    with pytest.raises(ValidationError): AppSpec(name=bad, image="redis")
```

- [ ] **Step 2: Run** `uv run pytest tests/test_apps_spec.py` — Expected: FAIL (module not found).

- [ ] **Step 3: Implement `spec.py` models and parsers.** `Mount.source` validated by a field validator: absolute path (starts with `/`) or bare name matching `^[A-Za-z0-9][A-Za-z0-9_.-]*$`; anything else (relative, `~`, contains `/`) fails. `AppSpec.name` validated against `NAME_RE`. Parsers wrap `ValidationError` into `InvalidSpec` with a readable message.

- [ ] **Step 4: Run** `uv run pytest tests/test_apps_spec.py` — Expected: PASS.

- [ ] **Step 5: Commit** — `git add src/cep/apps/spec.py tests/test_apps_spec.py && git commit -m "feat(apps): add runtime-neutral AppSpec and flag parsing"`

---

### Task 2: Presets and deploy-request resolution

**Files:**
- Modify: `src/cep/apps/spec.py`
- Create: `src/cep/apps/presets/{mongo,navidrome,nginx,postgres,redis,python}.yml`, `src/cep/apps/presets/__init__.py` (empty, so `importlib.resources` can find it)
- Modify: `pyproject.toml` (`[tool.setuptools.package-data]`: replace `"apps/app_templates/*.yaml"` with `"apps/presets/*.yml"`)
- Test: `tests/test_apps_spec.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces:
  - `DeployRequest(target: str, name: str|None=None, ports: list[Port]|None=None, env: dict[str,str]|None=None, mounts: list[Mount]|None=None, privileged: bool|None=None)`
  - `list_presets() -> list[str]` (sorted), `load_preset(name: str) -> AppSpec` (sets `preset=name`)
  - `default_name(ref: str) -> str` — raises `InvalidSpec`
  - `resolve(req: DeployRequest) -> AppSpec` — raises `InvalidSpec`

Preset files are `AppSpec` YAML without `preset`; translate the old templates in `src/cep/apps/app_templates/` 1:1 (image, ports, env, mounts, command as a list, workdir, `restart: true`). Compose named volumes become bare-name mounts. `name` is the template's service key (`mongodb`, `navidrome`, `nginx`, `postgres`, `redis`, `python-app`). `python` drops the `./app` mount and keeps `workdir: /app`, `command: [python, -m, http.server, "8069"]`. Do **not** port `ray-head.yml`.

`default_name` algorithm: drop `@digest`; if the text before the first `:` is in `KNOWN_REMOTE_PREFIXES`, drop it and the colon; take the last `/` segment; drop `:tag`; if the result doesn't match `NAME_RE`, raise `InvalidSpec("cannot derive an app name from '<ref>'; pass --name")`.

`resolve`: if `req.target in list_presets()` start from `load_preset`, else `AppSpec(name=req.name or default_name(req.target), image=req.target)`. Then: `env` merges key-wise (request wins); `ports`/`mounts` replace if not `None`; `name`/`privileged` replace if not `None`. Wrap any `ValidationError` into `InvalidSpec`.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_preset_loads():
    assert list_presets() == ["mongo", "navidrome", "nginx", "postgres", "python", "redis"]
    for p in list_presets():
        assert load_preset(p).preset == p

@pytest.mark.parametrize("ref,name", [
    ("redis", "redis"), ("redis:7-alpine", "redis"), ("docker:redis:7", "redis"),
    ("ghcr.io/foo/bar:1.0", "bar"), ("localhost:5000/foo/baz", "baz"),
    ("nginx@sha256:abc", "nginx"),
])
def test_default_name(ref, name):
    assert default_name(ref) == name

@pytest.mark.parametrize("ref", ["images:debian/12", "UPPER:1"])
def test_default_name_requires_explicit_name(ref):
    with pytest.raises(InvalidSpec, match="--name"): default_name(ref)

def test_resolve_image_ref():
    spec = resolve(DeployRequest(target="docker:redis:7", ports=[Port(host=1, container=2)]))
    assert (spec.name, spec.image, spec.preset, spec.ports) == ("redis", "docker:redis:7", None, [Port(host=1, container=2)])

def test_resolve_preset_env_merges_and_keeps_rest():
    base = load_preset("postgres")
    spec = resolve(DeployRequest(target="postgres", env={"POSTGRES_PASSWORD": "x"}))
    assert spec.env == {**base.env, "POSTGRES_PASSWORD": "x"}
    assert spec.ports == base.ports and spec.mounts == base.mounts and spec.preset == "postgres"

def test_resolve_preset_ports_replace():
    spec = resolve(DeployRequest(target="redis", ports=[]))
    assert spec.ports == []

def test_resolve_bypasses_preset_with_remote_prefix():
    assert resolve(DeployRequest(target="docker:redis")).preset is None
```

- [ ] **Step 2: Run** `uv run pytest tests/test_apps_spec.py` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** the functions and preset files described above. Presets load via `importlib.resources.files("cep.apps.presets")`.
- [ ] **Step 4: Run** `uv run pytest tests/test_apps_spec.py` — Expected: PASS.
- [ ] **Step 5: Commit** — `git add src/cep/apps/spec.py src/cep/apps/presets pyproject.toml tests/test_apps_spec.py && git commit -m "feat(apps): presets in AppSpec format and deploy request resolution"`

---

### Task 3: Runtime interface, command helper, runtime selection

**Files:**
- Create: `src/cep/apps/runtime/__init__.py`
- Test: `tests/test_apps_runtime.py`

**Interfaces:**
- Consumes: `AppSpec`, `AppStatus`, `InvalidSpec` from `cep.apps.spec`.
- Produces (in `cep.apps.runtime`):
  - `class UnsupportedSpec(InvalidSpec)`
  - `class CommandFailed(RuntimeError)` with attributes `argv: list[str]`, `stderr: str`; `str()` includes stderr
  - `run(argv: list[str]) -> str` — `subprocess.run(argv, capture_output=True, text=True)`; non-zero → `CommandFailed`; returns stdout
  - `class Runtime(Protocol)`: `deploy(self, spec: AppSpec) -> None`, `destroy(self, name: str) -> None`, `list(self) -> list[AppStatus]`
  - `get_runtime() -> Runtime` — `functools.cache`d; reads `CEP_APP_RUNTIME`; imports `DockerRuntime`/`IncusRuntime` lazily inside the function; unknown value → `ValueError` naming the allowed values

- [ ] **Step 1: Write the failing tests**

```python
def test_run_returns_stdout():
    assert run(["echo", "hi"]) == "hi\n"

def test_run_raises_with_stderr():
    with pytest.raises(CommandFailed, match="boom"):
        run(["sh", "-c", "echo boom >&2; exit 3"])

def test_get_runtime_rejects_unknown(monkeypatch):
    get_runtime.cache_clear()
    monkeypatch.setenv("CEP_APP_RUNTIME", "podman")
    with pytest.raises(ValueError, match="docker"): get_runtime()
    get_runtime.cache_clear()
```

(Selection of `docker`/`incus` is tested in Tasks 4 and 5 once those classes exist.)

- [ ] **Step 2: Run** `uv run pytest tests/test_apps_runtime.py` — Expected: FAIL.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(apps): Runtime protocol, command helper and runtime selection"`

---

### Task 4: DockerRuntime

**Files:**
- Create: `src/cep/apps/runtime/docker.py`
- Test: `tests/test_apps_docker_runtime.py`

**Interfaces:**
- Consumes: `run`, `UnsupportedSpec`, `Runtime` (Task 3); `INCUS_NATIVE_REMOTES` (Task 1).
- Produces: `class DockerRuntime` (no constructor args) implementing `Runtime`; pure module functions `resolve_image(ref: str) -> str`, `run_argv(spec: AppSpec) -> list[str]`, `parse_ps(stdout: str) -> list[AppStatus]`.

`resolve_image`: prefix before first `:` == `docker` → strip it; prefix in `INCUS_NATIVE_REMOTES` → `UnsupportedSpec("'<ref>' is an Incus image; the docker runtime only runs OCI images")`; else unchanged.

`run_argv` order is fixed (tests pin it): `docker run -d --name N --label cep.app=true [--label cep.preset=P] [-p H:C/proto]... [-e K=V]... [-v SRC:TGT[:ro]]... [--restart unless-stopped] [--privileged] [-w WD] IMAGE [COMMAND...]`.

`deploy`: `run(run_argv(spec))`. `destroy`: `run(["docker","rm","-f",name])`. `list`: `parse_ps(run(["docker","ps","-a","--filter","label=cep.app=true","--format","json"]))`. `docker ps --format json` emits one JSON object per line with keys `Names`, `Image`, `State`, `Labels` (`"k=v,k2=v2"`).

- [ ] **Step 1: Write the failing tests**

```python
def test_resolve_image():
    assert resolve_image("docker:redis:7") == "redis:7"
    assert resolve_image("ghcr.io/foo/bar:1.0") == "ghcr.io/foo/bar:1.0"
    with pytest.raises(UnsupportedSpec): resolve_image("images:debian/12")

def test_run_argv_full():
    spec = AppSpec(name="pg", image="docker:postgres:15", preset="postgres",
                   ports=[Port(host=5432, container=5432)], env={"A": "1"},
                   mounts=[Mount(source="pgdata", target="/data", read_only=True)],
                   privileged=True, workdir="/w", command=["postgres", "-c", "x=1"])
    assert run_argv(spec) == [
        "docker", "run", "-d", "--name", "pg",
        "--label", "cep.app=true", "--label", "cep.preset=postgres",
        "-p", "5432:5432/tcp", "-e", "A=1", "-v", "pgdata:/data:ro",
        "--restart", "unless-stopped", "--privileged", "-w", "/w",
        "postgres:15", "postgres", "-c", "x=1"]

def test_run_argv_minimal():
    assert run_argv(AppSpec(name="r", image="redis", restart=False)) == [
        "docker", "run", "-d", "--name", "r", "--label", "cep.app=true", "redis"]

def test_parse_ps():
    out = '{"Names":"r","Image":"redis","State":"running","Labels":"cep.app=true,cep.preset=redis"}\n' \
          '{"Names":"x","Image":"nginx","State":"exited","Labels":"cep.app=true"}\n'
    assert parse_ps(out) == [AppStatus(name="r", image="redis", state="running", preset="redis"),
                             AppStatus(name="x", image="nginx", state="exited")]
    assert parse_ps("") == []

def test_list_filters_on_label(monkeypatch):
    seen = []
    monkeypatch.setattr("cep.apps.runtime.docker.run", lambda argv: seen.append(argv) or "")
    DockerRuntime().list()
    assert "label=cep.app=true" in seen[0]

def test_get_runtime_docker_default(monkeypatch):
    get_runtime.cache_clear(); monkeypatch.delenv("CEP_APP_RUNTIME", raising=False)
    assert isinstance(get_runtime(), DockerRuntime); get_runtime.cache_clear()
```

- [ ] **Step 2: Run** `uv run pytest tests/test_apps_docker_runtime.py` — Expected: FAIL.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(apps): Docker runtime"`

---

### Task 5: IncusRuntime

**Files:**
- Create: `src/cep/apps/runtime/incus.py`
- Test: `tests/test_apps_incus_runtime.py`

**Interfaces:**
- Consumes: `run`, `CommandFailed`, `UnsupportedSpec` (Task 3).
- Produces:
  - `Remote(addr: str, protocol: str)` (small dataclass or pydantic model)
  - `resolve_image(ref: str, remotes: dict[str, Remote]) -> str`
  - `create_commands(spec: AppSpec, image: str) -> list[list[str]]` (create, device adds, start — no volume creation)
  - `parse_list(stdout: str) -> list[AppStatus]`
  - `class IncusRuntime(remotes: dict[str, Remote] | None = None)` — if `None`, loads from `incus remote list --format json` (shape: `{"alias": {"Addr": "...", "Protocol": "oci"|"simplestreams"|"incus", ...}}`).

`resolve_image` (first match wins):
1. prefix before first `:` is a key in `remotes` → ref unchanged.
2. ref contains `/` and its first segment contains `.` or `:` (registry host) → find a remote with `protocol == "oci"` whose `urlparse(addr).netloc == host` → `f"{alias}:{rest_after_host}"`; none → `UnsupportedSpec` containing `incus remote add <alias> https://<host> --protocol=oci`.
3. otherwise → the oci remote whose netloc is `docker.io` or `registry-1.docker.io` → `f"{alias}:{ref}"`; none → `UnsupportedSpec` containing `incus remote add docker https://docker.io --protocol=oci`.

`create_commands` order (tests pin it):
1. `["incus","create",image,name,"-c","user.cep.app=true", ("-c","user.cep.preset=P"), ("-c","environment.K=V")..., ("-c","boot.autostart=true") if restart, ("-c","security.privileged=true") if privileged, ("-c", "oci.entrypoint=" + shlex.join(command)) if command, ("-c","oci.cwd=WD") if workdir]`
2. per port: `["incus","config","device","add",name,f"port-{proto}-{host}","proxy",f"listen={proto}:0.0.0.0:{host}",f"connect={proto}:127.0.0.1:{container}"]`
3. per mount, index `i`: `["incus","config","device","add",name,f"mount-{i}","disk", f"source={src}", f"path={tgt}", ("pool=default" if volume), ("readonly=true" if ro)]`
4. `["incus","start",name]`

Before relying on `oci.entrypoint`/`oci.cwd`, verify on an Incus dev host that the server accepts them (`incus config set <oci-instance> oci.cwd /tmp`). If it doesn't, `create_commands` raises `UnsupportedSpec` when `command` or `workdir` is set instead, and the tests change accordingly.

`deploy(spec)`: resolve the image (all `UnsupportedSpec` before anything runs); for each volume mount, `run(["incus","storage","volume","show","default",src])` and on `CommandFailed` `run(["incus","storage","volume","create","default",src])`; then run `create_commands` in order. If any command after `create` fails, `run(["incus","delete","--force",name])` (ignore its failure) and re-raise the original.
`destroy`: `run(["incus","delete","--force",name])`. `list`: `parse_list(run(["incus","list","user.cep.app=true","--format","json"]))` — each item: `name`, `status` → `state`, `config["image.description"]` (default `""`) → `image`, `config.get("user.cep.preset")` → `preset`.

- [ ] **Step 1: Write the failing tests**

```python
REMOTES = {"docker": Remote("https://docker.io", "oci"), "ghcr": Remote("https://ghcr.io", "oci"),
           "images": Remote("https://images.linuxcontainers.org", "simplestreams")}

@pytest.mark.parametrize("ref,out", [
    ("redis:7", "docker:redis:7"), ("docker:redis:7", "docker:redis:7"),
    ("images:debian/12", "images:debian/12"), ("ghcr.io/foo/bar:1.0", "ghcr:foo/bar:1.0"),
])
def test_resolve_image(ref, out):
    assert resolve_image(ref, REMOTES) == out

def test_resolve_unknown_registry_hints():
    with pytest.raises(UnsupportedSpec, match="incus remote add .* https://quay.io --protocol=oci"):
        resolve_image("quay.io/a/b", REMOTES)

def test_resolve_no_dockerhub_remote_hints():
    with pytest.raises(UnsupportedSpec, match="https://docker.io --protocol=oci"):
        resolve_image("redis", {})

def test_create_commands():
    spec = AppSpec(name="pg", image="x", preset="postgres", env={"A": "1"}, privileged=True,
                   ports=[Port(host=5432, container=5432)],
                   mounts=[Mount(source="pgdata", target="/data"), Mount(source="/srv", target="/s", read_only=True)])
    assert create_commands(spec, "docker:postgres:15") == [
        ["incus", "create", "docker:postgres:15", "pg", "-c", "user.cep.app=true",
         "-c", "user.cep.preset=postgres", "-c", "environment.A=1",
         "-c", "boot.autostart=true", "-c", "security.privileged=true"],
        ["incus", "config", "device", "add", "pg", "port-tcp-5432", "proxy",
         "listen=tcp:0.0.0.0:5432", "connect=tcp:127.0.0.1:5432"],
        ["incus", "config", "device", "add", "pg", "mount-0", "disk", "source=pgdata", "path=/data", "pool=default"],
        ["incus", "config", "device", "add", "pg", "mount-1", "disk", "source=/srv", "path=/s", "readonly=true"],
        ["incus", "start", "pg"]]

def test_deploy_cleans_up_on_failure(monkeypatch):
    calls = []
    def fake_run(argv):
        calls.append(argv)
        if argv[:4] == ["incus", "config", "device", "add"]:
            raise CommandFailed(argv, "port in use")
        return ""
    monkeypatch.setattr("cep.apps.runtime.incus.run", fake_run)
    with pytest.raises(CommandFailed, match="port in use"):
        IncusRuntime(REMOTES).deploy(AppSpec(name="r", image="redis", ports=[Port(host=1, container=2)]))
    assert calls[-1] == ["incus", "delete", "--force", "r"]

def test_deploy_unsupported_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr("cep.apps.runtime.incus.run", lambda argv: calls.append(argv) or "")
    with pytest.raises(UnsupportedSpec):
        IncusRuntime({}).deploy(AppSpec(name="r", image="redis"))
    assert calls == []

def test_deploy_creates_missing_volume(monkeypatch):
    calls = []
    def fake_run(argv):
        calls.append(argv)
        if argv[:4] == ["incus", "storage", "volume", "show"]:
            raise CommandFailed(argv, "not found")
        return ""
    monkeypatch.setattr("cep.apps.runtime.incus.run", fake_run)
    IncusRuntime(REMOTES).deploy(AppSpec(name="r", image="redis", mounts=[Mount(source="v", target="/d")]))
    assert ["incus", "storage", "volume", "create", "default", "v"] in calls

def test_parse_list():
    out = json.dumps([{"name": "r", "status": "Running",
                       "config": {"image.description": "redis", "user.cep.preset": "redis"}}])
    assert parse_list(out) == [AppStatus(name="r", image="redis", state="Running", preset="redis")]

def test_get_runtime_incus(monkeypatch):
    get_runtime.cache_clear(); monkeypatch.setenv("CEP_APP_RUNTIME", "incus")
    monkeypatch.setattr("cep.apps.runtime.incus.run", lambda argv: "{}")
    assert isinstance(get_runtime(), IncusRuntime); get_runtime.cache_clear()
```

- [ ] **Step 2: Run** `uv run pytest tests/test_apps_incus_runtime.py` — Expected: FAIL.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(apps): Incus runtime"`

---

### Task 6: App-store endpoints on the Runtime; remove compose code

**Files:**
- Modify: `src/cep/apps/main.py` (app routes only; storage routes untouched), `src/cep/apps/store.py`
- Delete: `src/cep/apps/docker.py`, `src/cep/apps/utils.py`, `src/cep/apps/app_templates/`, `tests/test_docker.py`
- Test: `tests/test_apps_endpoints.py`

**Interfaces:**
- Consumes: `get_runtime`, `Runtime`, `CommandFailed` (Task 3); `DeployRequest`, `resolve`, `list_presets`, `AppStatus`, `InvalidSpec` (Tasks 1–2).
- Produces (HTTP, app-store service on :8080):
  - `POST /deploy` JSON body `DeployRequest` → `runtime.deploy(resolve(req))`; returns the deployed `AppSpec`
  - `GET /list` → `list[AppStatus]`
  - `DELETE /targetedDestroy?name=` → 404 if `name` not in `runtime.list()` names, else `runtime.destroy(name)`
  - `DELETE /clear` → `runtime.destroy` each app in `runtime.list()`; returns destroyed names
  - `GET /store/list` → `list_presets()`
  - `/debugUp` removed.
  - Exception handlers on the app: `InvalidSpec` → 422 `{"detail": str(e)}`; `CommandFailed` → 500 `{"detail": e.stderr}`.

- [ ] **Step 1: Write the failing tests** — a `FakeRuntime` with `apps: dict[str, AppSpec]`, `destroyed: list[str]`, `fail_with: Exception | None = None`; `deploy` raises `fail_with` if set, else stores; `destroy` pops and appends to `destroyed`; `list` returns `AppStatus(name, image, state="running", preset)` for each; fixture sets `app.dependency_overrides[get_runtime] = lambda: fake` and yields a `TestClient`.

```python
def test_deploy_preset_and_list(client, fake):
    r = client.post("/deploy", json={"target": "redis"})
    assert r.status_code == 200 and fake.apps["redis"].preset == "redis"
    assert client.get("/list").json() == [{"name": "redis", "image": "redis:7-alpine", "state": "running", "preset": "redis"}]

def test_deploy_invalid_is_422_and_nothing_deployed(client, fake):
    r = client.post("/deploy", json={"target": "images:debian/12"})
    assert r.status_code == 422 and "--name" in r.json()["detail"] and fake.apps == {}

def test_command_failure_is_500_with_stderr(client, fake):
    fake.fail_with = CommandFailed(["docker"], "name already in use")
    r = client.post("/deploy", json={"target": "redis"})
    assert r.status_code == 500 and "already in use" in r.json()["detail"]

def test_targeted_destroy_unknown_is_404(client, fake):
    assert client.delete("/targetedDestroy", params={"name": "cep-appstore"}).status_code == 404
    assert fake.destroyed == []

def test_clear_destroys_only_listed_apps(client, fake):
    client.post("/deploy", json={"target": "redis"}); client.post("/deploy", json={"target": "nginx"})
    assert sorted(client.delete("/clear").json()) == ["nginx", "redis"] and fake.apps == {}

def test_store_list(client):
    assert "redis" in client.get("/store/list").json()
```

(Adjust the image string in the first test to whatever `presets/redis.yml` holds.)

- [ ] **Step 2: Run** `uv run pytest tests/test_apps_endpoints.py` — Expected: FAIL.
- [ ] **Step 3: Implement** the routes and handlers; delete the listed files.
- [ ] **Step 4: Run the full suite** `uv run pytest` — Expected: all PASS, `grep -rn "cep.apps.docker\|app_templates" src tests` returns nothing.
- [ ] **Step 5: Commit** — `git add -A src/cep/apps tests && git commit -m "refactor(apps): endpoints use Runtime; drop compose deployment"`

---

### Task 7: Server proxy, CLI and README

**Files:**
- Modify: `src/cep/server/apps/__init__.py`, `src/cep/cli/apps/__init__.py`, `src/cep/apps/README.md`
- Test: `tests/test_cli_apps.py`

**Interfaces:**
- Consumes: app-store HTTP API (Task 6); `parse_port`, `parse_mount`, `parse_env`, `DeployRequest`, `InvalidSpec` (Tasks 1–2).
- Produces:
  - Proxy: `POST /apps/deployProxy` forwards its JSON body to `/deploy`; `GET /apps/listUpProxy`, `DELETE /apps/targetedDestroyProxy`, `DELETE /apps/clearProxy` unchanged; `/apps/debugUpProxy` removed. Proxies keep the existing `Response(content, status_code, headers)` pass-through so 404/422/500 reach the CLI.
  - CLI `build_deploy_request(target: str, name: str|None, port: list[str], env: list[str], volume: list[str], privileged: bool) -> DeployRequest` — empty lists → `None` (so presets aren't overridden), `privileged=False` → `None`.
  - `cep apps deploy TARGET [--name N] [--port P]... [--env K=V]... [--volume V]... [--privileged]` posts `build_deploy_request(...).model_dump(exclude_none=True)`; on a non-2xx response prints `detail` and exits 1. `cep apps list` prints one line per app: `name  state  image  [preset]`. `debug-up` command removed; `targeted-destroy` and `clear` kept.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_deploy_request_flags():
    req = build_deploy_request("redis", None, ["6380:6379"], ["A=1"], ["v:/d:ro"], False)
    assert req == DeployRequest(target="redis", ports=[Port(host=6380, container=6379)],
                                env={"A": "1"}, mounts=[Mount(source="v", target="/d", read_only=True)])

def test_build_deploy_request_no_flags_overrides_nothing():
    assert build_deploy_request("redis", None, [], [], [], False).model_dump(exclude_none=True) == {"target": "redis"}

def test_build_deploy_request_bad_flag():
    with pytest.raises(InvalidSpec): build_deploy_request("redis", None, ["nope"], [], [], False)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_cli_apps.py` — Expected: FAIL.
- [ ] **Step 3: Implement** proxy, CLI and README. README replaces "Docs TBA" with: `CEP_APP_RUNTIME` (docker|incus); image ref rules from the spec's *Image refs* section; Incus host prerequisite `incus remote add docker https://docker.io --protocol=oci` (and one per extra registry); for the Incus runtime, run the app store on the host (`CEP_APP_RUNTIME=incus uv run cep apps run`) since the `cep-appstore` container has no Incus client; the `cep.app` / `cep.preset` labels.
- [ ] **Step 4: Run the full suite** `uv run pytest` — Expected: all PASS.
- [ ] **Step 5: Manual smoke on a Docker dev box** — `uv run cep apps run` in one shell; in another: `cep apps deploy redis`, `cep apps list` (shows only `redis` with preset), `cep apps targeted-destroy cep-appstore` (404, nothing removed), `cep apps clear`. Record the output in the PR description.
- [ ] **Step 6: Commit** — `git add src/cep/server/apps src/cep/cli/apps src/cep/apps/README.md tests/test_cli_apps.py && git commit -m "feat(apps): proxy, CLI and docs for runtime-based deploys"`
