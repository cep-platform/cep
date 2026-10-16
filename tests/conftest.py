"""Shared fixtures for the CEP unit test suite."""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cep.apps.docker import PROXY_PORT_LABEL
from cep.datamodels import HostRecord, NetworkRecord, NetworkStore


# ---------------------------------------------------------------------------
# Isolated server DB (patches module-level globals in-place)
# ---------------------------------------------------------------------------

@pytest.fixture()
def server_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Redirect every server-side path reference to a fresh tmp directory so
    tests never touch real user data.
    """
    sdir = tmp_path / "server"
    sdir.mkdir()
    db_path = sdir / "db.json"

    monkeypatch.setattr("cep.server.utils.SERVER_DATA_DIR", sdir)
    monkeypatch.setattr("cep.server.utils.DB_PATH", db_path)
    monkeypatch.setattr("cep.server.network.SERVER_DATA_DIR", sdir)
    monkeypatch.setattr("cep.server.host.SERVER_DATA_DIR", sdir)

    return sdir


@pytest.fixture()
def mock_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Suppress all outbound DNS-service HTTP calls."""
    monkeypatch.setattr("cep.server.network.start_dns", lambda **kwargs: None)
    monkeypatch.setattr("cep.server.network.stop_dns", lambda: None)
    monkeypatch.setattr("cep.server.host.add_host_to_dns", lambda *a, **kw: None)
    monkeypatch.setattr("cep.server.host.remove_host_from_dns", lambda *a, **kw: None)
    monkeypatch.setattr("cep.server.apps.add_host_to_dns", lambda *a, **kw: None)
    monkeypatch.setattr("cep.server.apps.remove_host_from_dns", lambda *a, **kw: None)


@pytest.fixture()
def mock_create_ca(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace create_ca so no real nebula-cert subprocess is needed."""
    def _fake(name: str, ca_dir: Path) -> Path:
        (ca_dir / "ca.crt").write_text("fake-ca-cert")
        (ca_dir / "ca.key").write_text("fake-ca-key")
        return ca_dir

    monkeypatch.setattr("cep.server.network.create_ca", _fake)


# ---------------------------------------------------------------------------
# FastAPI TestClient (token-free, isolated DB)
# ---------------------------------------------------------------------------

@pytest.fixture()
def api(server_dir, mock_dns, mock_create_ca, monkeypatch) -> TestClient:
    """
    TestClient for the CEP main server with isolated DB and no auth.
    A fresh app instance is built so CEP_SERVER_TOKEN has no effect.
    """
    monkeypatch.delenv("CEP_SERVER_TOKEN", raising=False)

    from cep.server.main import instantiate_main_app
    from cep.server import network, host, dns, storage
    from cep.server.apps import apps_router

    app = instantiate_main_app()
    app.include_router(network.network_router)
    app.include_router(host.host_router)
    app.include_router(apps_router)
    app.include_router(dns.dns_router)
    app.include_router(storage.storage_router)

    return TestClient(app)


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

@pytest.fixture()
def cli_runner() -> CliRunner:
    """Typer CliRunner for invoking CLI commands in tests."""
    return CliRunner()


# ---------------------------------------------------------------------------
# Appstore + reverse proxy stubs for the /apps router
# ---------------------------------------------------------------------------

class FakeAppstoreResponse:
    """Minimal stand-in for an httpx.Response returned by the appstore."""

    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = json.dumps(self._json).encode()
        self.headers = {}

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self) -> dict:
        return self._json


class FakeAppstoreClient:
    """Configurable stand-in for the appstore httpx client in cep.server.apps."""

    def __init__(self):
        self.deploy_response = FakeAppstoreResponse(
            json_data={
                "services": {
                    "redis": {
                        "container_name": "cep-app-redis",
                        "labels": {PROXY_PORT_LABEL: "6379"},
                    }
                }
            }
        )
        self.destroy_response = FakeAppstoreResponse()
        self.deploy_error = None
        self.destroy_error = None
        self.deploy_calls: list[tuple] = []
        self.destroy_calls: list[tuple] = []

    def post(self, path: str, params: dict | None = None) -> FakeAppstoreResponse:
        self.deploy_calls.append((path, params))
        if self.deploy_error is not None:
            raise self.deploy_error
        return self.deploy_response

    def delete(self, path: str, params: dict | None = None) -> FakeAppstoreResponse:
        self.destroy_calls.append((path, params))
        if self.destroy_error is not None:
            raise self.destroy_error
        return self.destroy_response


@pytest.fixture()
def mock_appstore(monkeypatch: pytest.MonkeyPatch) -> FakeAppstoreClient:
    """Route all appstore calls made by the /apps router to a local stub."""
    stub = FakeAppstoreClient()
    monkeypatch.setattr("cep.server.apps.client", stub)
    return stub


class RproxyRecorder:
    """Records reverse proxy calls made by the /apps router."""

    def __init__(self):
        self.added: list[tuple[str, str]] = []
        self.removed: list[str] = []
        self.error = None

    def add_rproxy(self, hostname: str, destination: str) -> None:
        if self.error is not None:
            raise self.error
        self.added.append((hostname, destination))

    def remove_rproxy(self, hostname: str) -> None:
        if self.error is not None:
            raise self.error
        self.removed.append(hostname)


@pytest.fixture()
def mock_rproxy(monkeypatch: pytest.MonkeyPatch) -> RproxyRecorder:
    """Replace the reverse proxy used by the /apps router with a recorder."""
    recorder = RproxyRecorder()
    monkeypatch.setattr("cep.server.apps.CaddyReverseProxy", recorder)
    return recorder


# ---------------------------------------------------------------------------
# Pre-seeded DB helper
# ---------------------------------------------------------------------------

def seed_network(server_dir: Path, *, name: str = "testnet", dns: bool = False) -> NetworkRecord:
    """Write a network (no hosts) directly into the DB and create its dir."""
    from cep.server.utils import load_db, save_db

    net = NetworkRecord(
        name=name,
        subnet=ipaddress.IPv6Network("fd12:3456:789a:1::/64"),
        hosts={},
        dns=dns,
    )
    store = load_db()
    store.networks[name] = net
    save_db(store)
    (server_dir / name).mkdir(exist_ok=True)
    return net
