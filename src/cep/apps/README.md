# App store service

The app store service is where apps are provisioned and exposed to network nodes.
The app server calls are all routed through the main server behind proxies for security purposes as per the main README

## How deploys work

`cep apps deploy TARGET NETWORK` accepts three kinds of TARGET:

| TARGET | Example |
|---|---|
| a **preset** (`presets/<name>.yml`, `cep apps store list`) | `cep apps deploy redis net` |
| **any OCI image ref** plus flags | `cep apps deploy ghcr.io/foo/bar:1.0 net --port 8080:80 --env K=V --volume data:/data` |
| **your own compose file** (`.yml`/`.yaml`) | `cep apps deploy ./compose.yml net` |

Presets and image refs are a single-container `AppSpec` (`spec.py`). Flags
override a preset: `--env` merges key by key, `--port` / `--volume` replace
the preset's list. Use a full ref (`docker.io/library/redis`) to skip a preset
with the same name. Image refs resolve like Docker's (bare names go to
`docker.io`); other registries need an incus OCI remote.

Everything ends up as compose (`compose.py`). cep-main renders the request,
checks the app name against the network, and sends `{id, compose}` to the app
store, which runs it with `incus-compose` as a background job.

## Routing contract

caddy dials `<container_name>:<cep.proxy.port>` over the shared `cep` bridge,
so every deploy gets:

- one **routed** service with the `cep.proxy.port` label. For presets and
  image refs this is `--proxy-port`, or the first `--port` by default.
- a `container_name` for the routed service, `cep-app-<name>` unless your
  compose file sets one.
- every service on the external `cep` network, plus the `cep.app=true`
  label (and `cep.preset=<name>` for presets).

User compose files may define several services, but exactly one of them must
carry the `cep.proxy.port` label (or pass `--proxy-port` for a single-service
file). The app name defaults to the routed service's name (`--name` overrides
it). `--port`, `--env`, `--volume` and `--privileged` don't combine with a
compose file; edit the file instead.

TODO for v0.2:
 - Better logging
