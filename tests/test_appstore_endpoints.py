"""
Tests for the appstore app's own HTTP API (cep.apps.main).

These pin the contract that cep-main's /apps proxy consumes
(src/cep/server/apps/__init__.py):

- POST / with an AppInstallRequest JSON body installs the app and returns
  the template (services with container_name/labels) - 201
- POST / with an unknown template id 404s with an actionable detail
  (template dir + available apps)
- GET / lists deployed apps (raw incus JSON passthrough)
- GET /{app_id} returns app info
- DELETE /{app_id} tears the app down - 204

Regression: these routes were previously registered with an empty path
("@app.post('')"), which matches no URL - every call came back
404 {"detail": "Not Found"} even though the deploy proxy posted to "/".
The status assertions below fail against that old code.

All Incus subprocess work (incus/incus-compose) is monkeypatched; no
container runtime is needed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cep.apps.incus import ComposeConfig, Incus
from cep.apps.main import app as appstore_app

REDIS_TEMPLATE = ComposeConfig(
    services={
        "redis": {
            "container_name": "cep-app-redis",
            "labels": {"cep.proxy.port": "6379"},
        }
    }
)


class FakeIncus:
    """Records Incus calls made by the appstore; returns canned data."""

    def __init__(self):
        self.template = REDIS_TEMPLATE
        self.listed = [{"name": "cep-app-redis", "status": "Running"}]
        self.info_data = [{"name": "cep-app-redis", "status": "Running"}]
        self.calls: list[str] = []

    def get_app_template(self, name):
        self.calls.append(f"get_app_template:{name}")
        if self.template is None:
            raise ValueError(
                f"App {name} not found in template path /templates "
                "Available apps are ['redis']"
            )
        return self.template

    def add_to_deployment(self, app_id, app_config):
        self.calls.append(f"add_to_deployment:{app_id}")

    def remove_from_deployment(self, app_id):
        self.calls.append(f"remove_from_deployment:{app_id}")

    def compose_up(self, app_id):
        self.calls.append(f"compose_up:{app_id}")

    def compose_down(self, app_id):
        self.calls.append(f"compose_down:{app_id}")

    def list_(self):
        return self.listed

    def info(self, app_id):
        self.calls.append(f"info:{app_id}")
        return self.info_data


@pytest.fixture()
def fake_incus(monkeypatch: pytest.MonkeyPatch) -> FakeIncus:
    fake = FakeIncus()
    for attr in (
        "get_app_template",
        "add_to_deployment",
        "remove_from_deployment",
        "compose_up",
        "compose_down",
        "list_",
        "info",
    ):
        monkeypatch.setattr(Incus, attr, getattr(fake, attr))
    return fake


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Appstore TestClient with caddy bootstrap (lifespan) stubbed."""
    monkeypatch.setattr("cep.apps.main._init_caddy_with_retry", lambda: None)
    return TestClient(appstore_app)


class TestInstallApp:
    def test_post_root_installs_and_returns_template(self, client, fake_incus):
        """The deploy proxy posts to '/' and reads services from the body."""
        resp = client.post("/", json={"id": "redis", "config": {}})

        assert resp.status_code == 201
        assert resp.json()["services"]["redis"]["container_name"] == (
            "cep-app-redis"
        )
        assert fake_incus.calls == [
            "get_app_template:redis",
            "add_to_deployment:redis",
            "compose_up:redis",
        ]

    def test_post_root_with_unknown_app_404s_with_available_apps(
        self, client, fake_incus
    ):
        fake_incus.template = None

        resp = client.post("/", json={"id": "mongo", "config": {}})

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]
        assert "redis" in resp.json()["detail"], "detail must list available apps"
        assert fake_incus.calls == ["get_app_template:mongo"]


class TestListApp:
    def test_get_root_returns_incus_list_passthrough(self, client, fake_incus):
        resp = client.get("/")

        assert resp.status_code == 200
        assert resp.json() == fake_incus.listed


class TestGetApp:
    def test_get_app_id_returns_info(self, client, fake_incus):
        resp = client.get("/redis")

        assert resp.status_code == 200
        assert resp.json() == fake_incus.info_data


class TestUninstallApp:
    def test_delete_app_id_tears_down(self, client, fake_incus):
        resp = client.delete("/redis")

        assert resp.status_code == 204
        assert resp.content == b""
        assert fake_incus.calls == [
            "compose_down:redis",
            "remove_from_deployment:redis",
        ]


class TestHealth:
    def test_health_returns_ok_without_touching_incus(self, client, fake_incus):
        """compose.yml's healthcheck probes /health from inside the container
        during `incus-compose up` - before the incus trust registration - so
        it must answer without shelling out to incus.

        Also a regression guard for the route ordering: /health is registered
        above the /{app_id} catch-all; if it ever moves below, this request
        would be served by get_app("health") instead.
        """
        resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert fake_incus.calls == []
