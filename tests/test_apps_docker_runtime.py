"""Tests for DockerRuntime: ref resolution, argv construction and `docker ps` parsing."""
from __future__ import annotations

import pytest

from cep.apps.runtime import UnsupportedSpec, get_runtime
from cep.apps.runtime.docker import DockerRuntime, parse_ps, resolve_image, run_argv
from cep.apps.spec import AppSpec, AppStatus, Mount, Port


def test_resolve_image():
    assert resolve_image("docker:redis:7") == "redis:7"
    assert resolve_image("ghcr.io/foo/bar:1.0") == "ghcr.io/foo/bar:1.0"
    with pytest.raises(UnsupportedSpec):
        resolve_image("images:debian/12")


def test_run_argv_full():
    spec = AppSpec(
        name="pg", image="docker:postgres:15", preset="postgres",
        ports=[Port(host=5432, container=5432)], env={"A": "1"},
        mounts=[Mount(source="pgdata", target="/data", read_only=True)],
        privileged=True, workdir="/w", command=["postgres", "-c", "x=1"],
    )
    assert run_argv(spec) == [
        "docker", "run", "-d", "--name", "pg",
        "--label", "cep.app=true", "--label", "cep.preset=postgres",
        "-p", "5432:5432/tcp", "-e", "A=1", "-v", "pgdata:/data:ro",
        "--restart", "unless-stopped", "--privileged", "-w", "/w",
        "postgres:15", "postgres", "-c", "x=1",
    ]


def test_run_argv_minimal():
    assert run_argv(AppSpec(name="r", image="redis", restart=False)) == [
        "docker", "run", "-d", "--name", "r", "--label", "cep.app=true", "redis",
    ]


def test_parse_ps():
    out = (
        '{"Names":"r","Image":"redis","State":"running","Labels":"cep.app=true,cep.preset=redis"}\n'
        '{"Names":"x","Image":"nginx","State":"exited","Labels":"cep.app=true"}\n'
    )
    assert parse_ps(out) == [
        AppStatus(name="r", image="redis", state="running", preset="redis"),
        AppStatus(name="x", image="nginx", state="exited"),
    ]
    assert parse_ps("") == []


def test_list_filters_on_label(monkeypatch):
    seen = []
    monkeypatch.setattr("cep.apps.runtime.docker.run", lambda argv: seen.append(argv) or "")
    DockerRuntime().list()
    assert "label=cep.app=true" in seen[0]


def test_deploy_unsupported_runs_nothing(monkeypatch):
    seen = []
    monkeypatch.setattr("cep.apps.runtime.docker.run", lambda argv: seen.append(argv) or "")
    with pytest.raises(UnsupportedSpec):
        DockerRuntime().deploy(AppSpec(name="d", image="images:debian/12"))
    assert seen == []


def test_get_runtime_docker_default(monkeypatch):
    get_runtime.cache_clear()
    monkeypatch.delenv("CEP_APP_RUNTIME", raising=False)
    assert isinstance(get_runtime(), DockerRuntime)
    get_runtime.cache_clear()
