# App store service

The app store service is where apps are provisioned and exposed to network nodes.
The app server calls are all routed through the main server behind proxies for security purposes as per the main README

## How deploys work

An app is a single container described by an `AppSpec` (`spec.py`): image ref,
ports, env, mounts, command, workdir, restart, privileged. Specs come from either

- a **preset** in `presets/<name>.yml` (`cep apps deploy redis`), or
- **any image ref** plus flags
  (`cep apps deploy ghcr.io/foo/bar:1.0 --port 8080:80 --env K=V --volume data:/data`).

Flags override a preset: `--env` merges key by key; `--port` / `--volume`
replace the preset's list. Prefix a ref with `docker:` to skip a preset with the
same name (`docker:redis`).

The spec is handed to a `Runtime` (`runtime/`), chosen once per app-store
instance by `CEP_APP_RUNTIME`:

| Value | Runtime |
|---|---|
| `docker` (default) | one `docker run` per app |
| `incus` | `incus create` + proxy/disk devices + `incus start` |

Every container the app store creates is labelled `cep.app=true` (and
`cep.preset=<name>` when deployed from a preset); Docker uses labels, Incus
`user.cep.*` config keys. `list`, `targeted-destroy` and `clear` only ever see
labelled containers.

## Image refs

Refs follow Incus's `[remote:]image` convention.

- `redis:7`, `ghcr.io/foo/bar:1.0` — OCI images; work on both runtimes.
- `docker:redis:7` — explicit Docker Hub.
- `images:debian/12` — Incus-native image; Incus runtime only.

On Incus, bare Docker Hub refs go through the OCI remote pointing at
`docker.io`, and `registry.host/...` refs through the OCI remote whose URL
matches that host. Remotes are host setup and are never added automatically:

```sh
incus remote add docker https://docker.io --protocol=oci
incus remote add ghcr https://ghcr.io --protocol=oci   # one per extra registry
```

Named volumes (`--volume data:/data`) become custom volumes in the `default`
storage pool, created on first use. Mount sources must be absolute host paths
or volume names.

## Running with Incus

The `cep-appstore` container has no Incus client, so run the app store on the
Incus host instead:

```sh
CEP_APP_RUNTIME=incus uv run cep apps run
```

TODO for v0.2:
 - Better logging
