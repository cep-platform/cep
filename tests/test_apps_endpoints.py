"""Tests for the app-store endpoints, against an in-memory runtime."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cep.apps.main import app
from cep.apps.runtime import CommandFailed, get_runtime
from cep.apps.spec import AppSpec, AppStatus


class FakeRuntime:
    def __init__(self):
        self.apps: dict[str, AppSpec] = {}
        self.destroyed: list[str] = []
        self.fail_with: Exception | None = None

    def deploy(self, spec: AppSpec) -> None:
        if self.fail_with:
            raise self.fail_with
        self.apps[spec.name] = spec

    def destroy(self, name: str) -> None:
        self.apps.pop(name)
        self.destroyed.append(name)

    def list(self) -> list[AppStatus]:
        return [AppStatus(name=s.name, image=s.image, state="running", preset=s.preset)
                for s in self.apps.values()]


@pytest.fixture()
def fake():
    return FakeRuntime()


@pytest.fixture()
def client(fake):
    app.dependency_overrides[get_runtime] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_deploy_preset_and_list(client, fake):
    r = client.post("/deploy", json={"target": "redis"})
    assert r.status_code == 200 and fake.apps["redis"].preset == "redis"
    assert client.get("/list").json() == [
        {"name": "redis", "image": "redis:7-alpine", "state": "running", "preset": "redis"}
    ]


def test_deploy_image_with_overrides(client, fake):
    r = client.post("/deploy", json={"target": "ghcr.io/foo/bar:1.0",
                                     "ports": [{"host": 8080, "container": 80}]})
    assert r.status_code == 200 and r.json()["name"] == "bar"
    assert fake.apps["bar"].ports[0].host == 8080


def test_deploy_invalid_is_422_and_nothing_deployed(client, fake):
    r = client.post("/deploy", json={"target": "images:debian/12"})
    assert r.status_code == 422 and "--name" in r.json()["detail"]
    assert fake.apps == {}


def test_command_failure_is_500_with_stderr(client, fake):
    fake.fail_with = CommandFailed(["docker"], "name already in use")
    r = client.post("/deploy", json={"target": "redis"})
    assert r.status_code == 500 and "already in use" in r.json()["detail"]


def test_targeted_destroy(client, fake):
    client.post("/deploy", json={"target": "redis"})
    assert client.delete("/targetedDestroy", params={"name": "redis"}).status_code == 200
    assert fake.destroyed == ["redis"]


def test_targeted_destroy_unknown_is_404(client, fake):
    assert client.delete("/targetedDestroy", params={"name": "cep-appstore"}).status_code == 404
    assert fake.destroyed == []


def test_clear_destroys_only_listed_apps(client, fake):
    client.post("/deploy", json={"target": "redis"})
    client.post("/deploy", json={"target": "nginx"})
    assert sorted(client.delete("/clear").json()) == ["nginx", "redis"]
    assert fake.apps == {}


def test_store_list(client):
    assert "redis" in client.get("/store/list").json()
