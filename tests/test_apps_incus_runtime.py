"""Tests for IncusRuntime: ref resolution, command construction, rollback and listing."""
from __future__ import annotations

import json

import pytest

from cep.apps.runtime import CommandFailed, UnsupportedSpec, get_runtime
from cep.apps.runtime.incus import IncusRuntime, Remote, create_commands, parse_list, resolve_image
from cep.apps.spec import AppSpec, AppStatus, Mount, Port

REMOTES = {
    "docker": Remote("https://docker.io", "oci"),
    "ghcr": Remote("https://ghcr.io", "oci"),
    "images": Remote("https://images.linuxcontainers.org", "simplestreams"),
}


@pytest.mark.parametrize("ref,out", [
    ("redis:7", "docker:redis:7"),
    ("docker:redis:7", "docker:redis:7"),
    ("images:debian/12", "images:debian/12"),
    ("ghcr.io/foo/bar:1.0", "ghcr:foo/bar:1.0"),
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
    spec = AppSpec(
        name="pg", image="x", preset="postgres", env={"A": "1"}, privileged=True,
        ports=[Port(host=5432, container=5432)],
        mounts=[Mount(source="pgdata", target="/data"), Mount(source="/srv", target="/s", read_only=True)],
    )
    assert create_commands(spec, "docker:postgres:15") == [
        ["incus", "create", "docker:postgres:15", "pg", "-c", "user.cep.app=true",
         "-c", "user.cep.preset=postgres", "-c", "environment.A=1",
         "-c", "boot.autostart=true", "-c", "security.privileged=true"],
        ["incus", "config", "device", "add", "pg", "port-tcp-5432", "proxy",
         "listen=tcp:0.0.0.0:5432", "connect=tcp:127.0.0.1:5432"],
        ["incus", "config", "device", "add", "pg", "mount-0", "disk",
         "source=pgdata", "path=/data", "pool=default"],
        ["incus", "config", "device", "add", "pg", "mount-1", "disk",
         "source=/srv", "path=/s", "readonly=true"],
        ["incus", "start", "pg"],
    ]


def test_create_commands_command_and_workdir():
    spec = AppSpec(name="p", image="x", restart=False, workdir="/app",
                   command=["python", "-m", "http.server", "8069"])
    assert create_commands(spec, "docker:python")[0] == [
        "incus", "create", "docker:python", "p", "-c", "user.cep.app=true",
        "-c", "oci.entrypoint=python -m http.server 8069", "-c", "oci.cwd=/app",
    ]


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


def test_deploy_failed_create_does_not_delete(monkeypatch):
    calls = []

    def fake_run(argv):
        calls.append(argv)
        raise CommandFailed(argv, "instance already exists")

    monkeypatch.setattr("cep.apps.runtime.incus.run", fake_run)
    with pytest.raises(CommandFailed, match="already exists"):
        IncusRuntime(REMOTES).deploy(AppSpec(name="r", image="redis"))
    assert ["incus", "delete", "--force", "r"] not in calls


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


def test_list_filters_on_label(monkeypatch):
    seen = []
    monkeypatch.setattr("cep.apps.runtime.incus.run", lambda argv: seen.append(argv) or "[]")
    assert IncusRuntime(REMOTES).list() == []
    assert "user.cep.app=true" in seen[0]


def test_get_runtime_incus(monkeypatch):
    get_runtime.cache_clear()
    monkeypatch.setenv("CEP_APP_RUNTIME", "incus")
    monkeypatch.setattr("cep.apps.runtime.incus.run", lambda argv: "{}")
    assert isinstance(get_runtime(), IncusRuntime)
    get_runtime.cache_clear()
