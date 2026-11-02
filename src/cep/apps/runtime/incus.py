"""Incus runtime: OCI images via OCI remotes, plus Incus-native images."""
from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from urllib.parse import urlparse

from cep.apps.runtime import CommandFailed, UnsupportedSpec, run
from cep.apps.spec import AppSpec, AppStatus

POOL = "default"
DOCKER_HUB_HOSTS = {"docker.io", "registry-1.docker.io"}


@dataclass(frozen=True)
class Remote:
    addr: str
    protocol: str


def _oci_remote_for(host_names: set[str], remotes: dict[str, Remote]) -> str | None:
    for alias, r in remotes.items():
        if r.protocol == "oci" and urlparse(r.addr).netloc in host_names:
            return alias
    return None


def resolve_image(ref: str, remotes: dict[str, Remote]) -> str:
    prefix, sep, _ = ref.partition(":")
    if sep and prefix in remotes:
        return ref

    host, slash, rest = ref.partition("/")
    if slash and ("." in host or ":" in host):
        alias = _oci_remote_for({host}, remotes)
        if alias is None:
            raise UnsupportedSpec(
                f"no Incus OCI remote for registry '{host}'; add one with "
                f"`incus remote add <alias> https://{host} --protocol=oci`"
            )
        return f"{alias}:{rest}"

    alias = _oci_remote_for(DOCKER_HUB_HOSTS, remotes)
    if alias is None:
        raise UnsupportedSpec(
            "no Incus OCI remote for Docker Hub; add one with "
            "`incus remote add docker https://docker.io --protocol=oci`"
        )
    return f"{alias}:{ref}"


def create_commands(spec: AppSpec, image: str) -> list[list[str]]:
    """Create the instance stopped, attach its devices, then start it."""
    config = ["user.cep.app=true"]
    if spec.preset:
        config.append(f"user.cep.preset={spec.preset}")
    config += [f"environment.{k}={v}" for k, v in spec.env.items()]
    if spec.restart:
        config.append("boot.autostart=true")
    if spec.privileged:
        config.append("security.privileged=true")
    if spec.command:
        config.append(f"oci.entrypoint={shlex.join(spec.command)}")
    if spec.workdir:
        config.append(f"oci.cwd={spec.workdir}")

    create = ["incus", "create", image, spec.name]
    for c in config:
        create += ["-c", c]

    add = ["incus", "config", "device", "add", spec.name]
    commands = [create]
    for p in spec.ports:
        commands.append(add + [
            f"port-{p.protocol}-{p.host}", "proxy",
            f"listen={p.protocol}:0.0.0.0:{p.host}",
            f"connect={p.protocol}:127.0.0.1:{p.container}",
        ])
    for i, m in enumerate(spec.mounts):
        commands.append(add + [
            f"mount-{i}", "disk", f"source={m.source}", f"path={m.target}",
            *(["pool=" + POOL] if m.is_volume else []),
            *(["readonly=true"] if m.read_only else []),
        ])
    commands.append(["incus", "start", spec.name])
    return commands


def parse_list(stdout: str) -> list[AppStatus]:
    return [
        AppStatus(
            name=i["name"],
            image=i.get("config", {}).get("image.description", ""),
            state=i["status"],
            preset=i.get("config", {}).get("user.cep.preset"),
        )
        for i in json.loads(stdout or "[]")
    ]


def load_remotes() -> dict[str, Remote]:
    raw = json.loads(run(["incus", "remote", "list", "--format", "json"]))
    return {k: Remote(v["Addr"], v["Protocol"]) for k, v in raw.items()}


class IncusRuntime:
    def __init__(self, remotes: dict[str, Remote] | None = None):
        """`remotes` pins the remote list (tests); otherwise it is re-read on every
        deploy, so `incus remote add ...` takes effect without a restart."""
        self._remotes = remotes

    def deploy(self, spec: AppSpec) -> None:
        remotes = self._remotes if self._remotes is not None else load_remotes()
        create, *rest = create_commands(spec, resolve_image(spec.image, remotes))

        for m in spec.mounts:
            if m.is_volume:
                try:
                    run(["incus", "storage", "volume", "show", POOL, m.source])
                except CommandFailed:
                    run(["incus", "storage", "volume", "create", POOL, m.source])

        run(create)
        try:
            for argv in rest:
                run(argv)
        except CommandFailed:
            try:
                run(["incus", "delete", "--force", spec.name])
            except CommandFailed:
                pass
            raise

    def destroy(self, name: str) -> None:
        run(["incus", "delete", "--force", name])

    def list(self) -> list[AppStatus]:
        return parse_list(run(["incus", "list", "user.cep.app=true", "--format", "json"]))
