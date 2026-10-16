"""
Tests for the /apps deploy and destroy proxy endpoints.

deployProxy:
- Happy path wires reverse proxy + DNS record + AppRecord into the DB
- Reverse proxy dial target comes from the template's container_name
- 404 for an unknown network
- 409 when the app is already deployed in the network
- 409 when the network has no cep host
- Appstore errors propagate; DB stays untouched
- 500 when the template lacks container_name / proxy-port label
- 500 when the template defines more than one service
- 502 when the reverse proxy or appstore is unreachable

targetedDestroyProxy:
- Happy path removes reverse proxy route + DNS record + AppRecord
- Destroy removes exactly the route that deploy added (hostname symmetry)
- 404 for an unknown network or an app that is not deployed
- Appstore errors propagate; no cleanup happens
- 502 when the reverse proxy is unreachable; DB stays untouched

All HTTP is stubbed via conftest fixtures (mock_appstore, mock_rproxy).
"""
from __future__ import annotations

import ipaddress

import httpx
import pytest
import requests

from cep.datamodels import AppRecord, HostRecord
from cep.server.utils import load_db, save_db
from tests.conftest import FakeAppstoreResponse, seed_network


CEP_HOST_IP = "fd12:3456:789a:1::1"


def _seed_cep_host(network_name: str = "testnet", host_name: str = "cep") -> None:
    """Add the network's first host (::1) directly into the DB."""
    store = load_db()
    store.networks[network_name].hosts[host_name] = HostRecord(
        name=host_name,
        ip=ipaddress.ip_address(CEP_HOST_IP),
        groups=[],
        is_lighthouse=False,
    )
    save_db(store)


def _seed_deployed_app(
    network_name: str = "testnet",
    app_name: str = "redis",
) -> None:
    """Mark an app as deployed in the network's DB record."""
    store = load_db()
    store.networks[network_name].apps[app_name] = AppRecord(
        name=app_name,
        ip=ipaddress.ip_address(CEP_HOST_IP),
    )
    save_db(store)


def _dns_recorder(monkeypatch: pytest.MonkeyPatch, calls: list) -> None:
    monkeypatch.setattr(
        "cep.server.apps.add_host_to_dns",
        lambda req: calls.append(req),
    )
    monkeypatch.setattr(
        "cep.server.apps.remove_host_from_dns",
        lambda name: calls.append(name),
    )


# ---------------------------------------------------------------------------
# /apps/deployProxy
# ---------------------------------------------------------------------------

class TestDeployProxy:
    def test_happy_path_wires_rproxy_dns_and_db(
        self, api, server_dir, mock_appstore, mock_rproxy, monkeypatch
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        dns_calls = []
        _dns_recorder(monkeypatch, dns_calls)

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 200
        assert mock_appstore.deploy_calls == [("/deploy", {"name": "redis"})]
        assert resp.json()["services"]["redis"]["container_name"] == "cep-app-redis"
        assert mock_rproxy.added == [("redis.cep.testnet", "cep-app-redis:6379")], (
            "dial target must be container_name:proxy_port from the template"
        )
        assert len(dns_calls) == 1
        assert dns_calls[0].name == "redis.cep.testnet"
        assert dns_calls[0].ip == CEP_HOST_IP
        store = load_db()
        app = store.networks["testnet"].apps["redis"]
        assert app.name == "redis"
        assert app.ip == ipaddress.ip_address(CEP_HOST_IP)

    def test_returns_404_for_unknown_network(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "ghost"},
        )

        assert resp.status_code == 404
        assert mock_appstore.deploy_calls == []
        assert mock_rproxy.added == []

    def test_returns_409_when_app_already_deployed(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        _seed_deployed_app()

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 409
        assert "already deployed" in resp.json()["detail"]
        assert mock_appstore.deploy_calls == []

    def test_returns_409_when_network_has_no_cep_host(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        seed_network(server_dir, name="testnet")

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 409
        assert "no cep host" in resp.json()["detail"]
        assert mock_appstore.deploy_calls == []

    def test_appstore_error_propagates_and_db_unchanged(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        mock_appstore.deploy_response = FakeAppstoreResponse(
            status_code=404,
            json_data={"detail": "App 'redis' not found in template path"},
        )

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "App 'redis' not found in template path"
        assert mock_rproxy.added == []
        assert load_db().networks["testnet"].apps == {}

    def test_returns_500_when_template_misses_proxy_metadata(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        mock_appstore.deploy_response = FakeAppstoreResponse(
            json_data={"services": {"redis": {"image": "redis:7"}}},
        )

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 500
        assert "container_name" in resp.json()["detail"]
        assert mock_rproxy.added == []
        assert load_db().networks["testnet"].apps == {}

    def test_returns_500_when_template_has_multiple_services(
        self, api, server_dir, mock_appstore
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        mock_appstore.deploy_response = FakeAppstoreResponse(
            json_data={
                "services": {
                    "redis": {"container_name": "cep-app-redis", "labels": {"cep.proxy.port": "6379"}},
                    "sidecar": {"container_name": "cep-app-sidecar", "labels": {"cep.proxy.port": "80"}},
                }
            },
        )

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 500
        assert "exactly one service" in resp.json()["detail"]

    def test_returns_502_when_rproxy_unreachable(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        mock_rproxy.error = requests.exceptions.ConnectionError("caddy down")

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 502
        assert load_db().networks["testnet"].apps == {}

    def test_returns_502_when_appstore_unreachable(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        mock_appstore.deploy_error = httpx.ConnectError("appstore down")

        resp = api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 502
        assert mock_rproxy.added == []
        assert load_db().networks["testnet"].apps == {}


# ---------------------------------------------------------------------------
# /apps/targetedDestroyProxy
# ---------------------------------------------------------------------------

class TestTargetedDestroyProxy:
    def test_happy_path_removes_rproxy_dns_and_record(
        self, api, server_dir, mock_appstore, mock_rproxy, monkeypatch
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        _seed_deployed_app()
        dns_calls = []
        _dns_recorder(monkeypatch, dns_calls)

        resp = api.delete(
            "/apps/targetedDestroyProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 200
        assert mock_appstore.destroy_calls == [
            ("/targetedDestroy", {"name": "redis"})
        ]
        assert mock_rproxy.removed == ["redis.cep.testnet"]
        assert dns_calls == ["redis.cep.testnet"]
        assert "redis" not in load_db().networks["testnet"].apps

    def test_destroy_removes_the_route_deploy_added(
        self, api, server_dir, mock_appstore, mock_rproxy, monkeypatch
    ):
        """Regression: deploy and destroy must use the same hostname."""
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        dns_calls = []
        _dns_recorder(monkeypatch, dns_calls)

        api.post(
            "/apps/deployProxy",
            params={"name": "redis", "network_name": "testnet"},
        )
        api.delete(
            "/apps/targetedDestroyProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        added_hostnames = [hostname for hostname, _ in mock_rproxy.added]
        assert mock_rproxy.removed == added_hostnames
        assert dns_calls[-1] == added_hostnames[0]

    def test_returns_404_for_unknown_network(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        resp = api.delete(
            "/apps/targetedDestroyProxy",
            params={"name": "redis", "network_name": "ghost"},
        )

        assert resp.status_code == 404
        assert mock_appstore.destroy_calls == []
        assert mock_rproxy.removed == []

    def test_returns_404_when_app_not_deployed(
        self, api, server_dir, mock_appstore, mock_rproxy
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()

        resp = api.delete(
            "/apps/targetedDestroyProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 404
        assert "not deployed" in resp.json()["detail"]
        assert mock_appstore.destroy_calls == []

    def test_appstore_error_propagates_and_no_cleanup(
        self, api, server_dir, mock_appstore, mock_rproxy, monkeypatch
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        _seed_deployed_app()
        dns_calls = []
        _dns_recorder(monkeypatch, dns_calls)
        mock_appstore.destroy_response = FakeAppstoreResponse(
            status_code=500,
            json_data={"detail": "docker daemon lost"},
        )

        resp = api.delete(
            "/apps/targetedDestroyProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 500
        assert resp.json()["detail"] == "docker daemon lost"
        assert mock_rproxy.removed == []
        assert dns_calls == []
        assert "redis" in load_db().networks["testnet"].apps

    def test_returns_502_when_rproxy_unreachable(
        self, api, server_dir, mock_appstore, mock_rproxy, monkeypatch
    ):
        seed_network(server_dir, name="testnet")
        _seed_cep_host()
        _seed_deployed_app()
        dns_calls = []
        _dns_recorder(monkeypatch, dns_calls)
        mock_rproxy.error = requests.exceptions.ConnectionError("caddy down")

        resp = api.delete(
            "/apps/targetedDestroyProxy",
            params={"name": "redis", "network_name": "testnet"},
        )

        assert resp.status_code == 502
        assert dns_calls == []
        assert "redis" in load_db().networks["testnet"].apps