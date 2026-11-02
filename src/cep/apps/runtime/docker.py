"""Docker runtime: one `docker run` per app. Temporary, removed once Incus replaces Docker."""
from __future__ import annotations

import json

from cep.apps.runtime import UnsupportedSpec, run
from cep.apps.spec import INCUS_NATIVE_REMOTES, AppSpec, AppStatus

APP_LABEL = "cep.app=true"


def resolve_image(ref: str) -> str:
    prefix, sep, rest = ref.partition(":")
    if sep and prefix == "docker":
        return rest
    if sep and prefix in INCUS_NATIVE_REMOTES:
        raise UnsupportedSpec(f"'{ref}' is an Incus image; the docker runtime only runs OCI images")
    return ref


def run_argv(spec: AppSpec) -> list[str]:
    argv = ["docker", "run", "-d", "--name", spec.name, "--label", APP_LABEL]
    if spec.preset:
        argv += ["--label", f"cep.preset={spec.preset}"]
    for p in spec.ports:
        argv += ["-p", f"{p.host}:{p.container}/{p.protocol}"]
    for k, v in spec.env.items():
        argv += ["-e", f"{k}={v}"]
    for m in spec.mounts:
        argv += ["-v", f"{m.source}:{m.target}" + (":ro" if m.read_only else "")]
    if spec.restart:
        argv += ["--restart", "unless-stopped"]
    if spec.privileged:
        argv.append("--privileged")
    if spec.workdir:
        argv += ["-w", spec.workdir]
    return argv + [resolve_image(spec.image), *(spec.command or [])]


def parse_ps(stdout: str) -> list[AppStatus]:
    apps = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        labels = dict(kv.split("=", 1) for kv in c.get("Labels", "").split(",") if "=" in kv)
        apps.append(
            AppStatus(name=c["Names"], image=c["Image"], state=c["State"], preset=labels.get("cep.preset"))
        )
    return apps


class DockerRuntime:
    def deploy(self, spec: AppSpec) -> None:
        run(run_argv(spec))

    def destroy(self, name: str) -> None:
        run(["docker", "rm", "-f", name])

    def list(self) -> list[AppStatus]:
        return parse_ps(run(["docker", "ps", "-a", "--filter", f"label={APP_LABEL}", "--format", "json"]))
