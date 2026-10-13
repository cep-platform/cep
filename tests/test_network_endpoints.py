"""
Tests for the /network/delete, /network/show, and /network/lighthouses router endpoints.

TODO references:
  server/network.py:73  – "make sure network_record deletion is tested"
  server/network.py:100 – "create dummy database and check if the contents match the spec"
  server/network.py:117 – "test lighthouses implicitly in an integration test"

delete:
- Removes the network directory from SERVER_DATA_DIR
- Removes the network record from the DB
- Returns 404 when the directory does not exist
- Returns 404 when the record is not in the DB (but directory exists)
- Calls stop_dns only when the network had DNS enabled

show:
- Returns the full NetworkRecord (name, subnet, dns flag, hosts)
- Returned subnet matches exactly what was stored
- Returned dns flag matches exactly what was stored
- Returns 404 for an unknown network name

lighthouses:
- Returns empty dict when no hosts are lighthouses
- Returns IPv4 lighthouse as "ip:4242"
- Returns IPv6 lighthouse as "[ip]:4242"
- Non-lighthouse hosts are excluded from the mapping
- Returns 404 for an unknown network name

create (happy path):
- Takes a NetworkCreateRequest body via POST; returns the persisted record
- Writes the CA into the data dir and saves the DB record
- Starts DNS only when dns=True

create (duplicate guards):
- Returns 409 when the name is already in the DB; existing hosts, subnet,
  and CA files are untouched and create_ca is never invoked
- Returns 409 when a data dir exists without a DB record (orphan dir)

create (CA failure path):
- Returns 500 with nebula-cert stderr and persists no DB record when CA
  creation fails (create_ca unit tests live in test_network_helpers.py)
- Removes the data dir it just created so /network/list (which reads the
  data dir, not the DB) stays in sync with the DB

(Pre-existing data dirs never reach the CA step: the duplicate/orphan
guards above reject them with 409 first, contents untouched.)
"""
from __future__ import annotations

import ipaddress
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from cep.datamodels import HostRecord, NetworkRecord, NetworkStore
from cep.server.utils import load_db, save_db
from tests.conftest import seed_network


@pytest.fixture()
def api_real_ca(server_dir, mock_dns, monkeypatch) -> TestClient:
    """TestClient for the network router with the real create_ca in place."""
    monkeypatch.delenv("CEP_SERVER_TOKEN", raising=False)

    from cep.server.main import instantiate_main_app
    from cep.server import network

    app = instantiate_main_app()
    app.include_router(network.network_router)

    return TestClient(app)


class TestNetworkCreateCaFailure:
    def test_create_endpoint_returns_500_and_saves_nothing_when_ca_fails(self, api_real_ca, server_dir, monkeypatch):
        error = subprocess.CalledProcessError(1, cmd=["nebula-cert"], stderr="boom")
        monkeypatch.setattr("cep.server.network.get_executable_path", lambda name: "/fake/nebula-cert")
        monkeypatch.setattr("cep.server.network.subprocess.run", MagicMock(side_effect=error))

        resp = api_real_ca.post("/network/create", json={"name": "failnet", "dns": False})

        assert resp.status_code == 500
        assert "boom" in resp.json()["detail"]
        store = load_db()
        assert "failnet" not in store.networks, "Failed CA creation must not persist a network record"
        assert not (server_dir / "failnet").exists(), \
            "Failed CA creation must not leave an empty data dir behind (phantom entry in /network/list)"

class TestNetworkCreate:
    def test_returns_record_and_persists_state(self, api, server_dir):
        resp = api.post("/network/create", json={"name": "newnet", "dns": False})

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "newnet"
        assert body["hosts"] == {}

        store = load_db()
        assert "newnet" in store.networks, "Created network must be persisted in the DB"
        assert (server_dir / "newnet" / "ca.crt").read_text() == "fake-ca-cert"
        assert (server_dir / "newnet" / "ca.key").read_text() == "fake-ca-key"

    def test_starts_dns_only_when_enabled(self, api, server_dir, monkeypatch):
        start_calls = []
        monkeypatch.setattr("cep.server.network.start_dns", lambda **kwargs: start_calls.append(kwargs))

        resp_on = api.post("/network/create", json={"name": "dnsnet", "dns": True})
        resp_off = api.post("/network/create", json={"name": "quietnet", "dns": False})

        assert resp_on.status_code == 200
        assert resp_off.status_code == 200
        assert start_calls == [{"subnet": resp_on.json()["subnet"]}], \
            "start_dns must run exactly once, for the dns=True network"


class TestNetworkCreateDuplicate:
    def test_returns_409_and_preserves_existing_network(self, api, server_dir):
        seed_network(server_dir, name="mynet")
        _seed_node(server_dir, network_name="mynet", host_name="node1")
        net_dir = server_dir / "mynet"
        (net_dir / "ca.crt").write_text("original-ca")

        resp = api.post("/network/create", json={"name": "mynet", "dns": False})

        assert resp.status_code == 409
        record = load_db().networks["mynet"]
        assert list(record.hosts) == ["node1"], "Duplicate create must not wipe existing hosts"
        assert str(record.subnet) == "fd12:3456:789a:1::/64", "Duplicate create must not change the subnet"
        assert (net_dir / "ca.crt").read_text() == "original-ca", \
            "Duplicate create must not regenerate the CA"

    def test_create_ca_is_not_invoked_on_duplicate(self, api, server_dir, monkeypatch):
        seed_network(server_dir, name="mynet")
        calls = []
        monkeypatch.setattr("cep.server.network.create_ca", lambda *a, **kw: calls.append((a, kw)))

        resp = api.post("/network/create", json={"name": "mynet", "dns": False})

        assert resp.status_code == 409
        assert calls == [], "create_ca must not run when the network already exists"

    def test_returns_409_for_orphan_data_dir(self, api, server_dir):
        orphan = server_dir / "orphannet"
        orphan.mkdir()
        (orphan / "ca.crt").write_text("leftover-ca")

        resp = api.post("/network/create", json={"name": "orphannet", "dns": False})

        assert resp.status_code == 409
        assert "orphannet" not in load_db().networks, "Orphan-dir create must not persist a DB record"
        assert (orphan / "ca.crt").read_text() == "leftover-ca", "Orphan dir contents must be untouched"


class TestNetworkDelete:
    def test_directory_is_removed_after_delete(self, api, server_dir):
        seed_network(server_dir, name="mynet")
        net_dir = server_dir / "mynet"
        assert net_dir.exists()

        api.delete("/network/delete", params={"name": "mynet"})

        assert not net_dir.exists(), "Network directory must be deleted"

    def test_db_record_is_removed_after_delete(self, api, server_dir):
        seed_network(server_dir, name="mynet")

        api.delete("/network/delete", params={"name": "mynet"})

        store = load_db()
        assert "mynet" not in store.networks, "Network record must be removed from DB"

    def test_returns_404_when_directory_missing(self, api, server_dir):
        # Insert DB record but intentionally omit the directory
        net = NetworkRecord(name="ghost", subnet="fd00::/64", hosts={}, dns=False)
        store = NetworkStore(networks={"ghost": net})
        save_db(store)
        # directory NOT created

        resp = api.delete("/network/delete", params={"name": "ghost"})
        assert resp.status_code == 404

    def test_returns_404_when_record_not_in_db(self, api, server_dir):
        # Create directory but no DB record
        (server_dir / "orphan").mkdir()

        resp = api.delete("/network/delete", params={"name": "orphan"})
        assert resp.status_code == 404

    def test_stop_dns_called_when_dns_enabled(self, api, server_dir, monkeypatch):
        seed_network(server_dir, name="dnsnet", dns=True)
        stop_calls = []
        monkeypatch.setattr("cep.server.network.stop_dns", lambda: stop_calls.append(True))

        api.delete("/network/delete", params={"name": "dnsnet"})

        assert len(stop_calls) == 1, "stop_dns must be called when network had DNS enabled"

    def test_stop_dns_not_called_when_dns_disabled(self, api, server_dir, monkeypatch):
        seed_network(server_dir, name="nodnsnet", dns=False)
        stop_calls = []
        monkeypatch.setattr("cep.server.network.stop_dns", lambda: stop_calls.append(True))

        api.delete("/network/delete", params={"name": "nodnsnet"})

        assert len(stop_calls) == 0, "stop_dns must NOT be called when DNS was disabled"


class TestNetworkShow:
    def test_returns_correct_name(self, api, server_dir):
        seed_network(server_dir, name="mynet")
        resp = api.get("/network/show", params={"name": "mynet"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "mynet"

    def test_returned_subnet_matches_stored_value(self, api, server_dir):
        seed_network(server_dir, name="mynet")
        resp = api.get("/network/show", params={"name": "mynet"})
        assert resp.status_code == 200
        # seed_network always uses fd12:3456:789a:1::/64
        assert resp.json()["subnet"] == "fd12:3456:789a:1::/64"

    def test_returned_dns_flag_matches_stored_true(self, api, server_dir):
        seed_network(server_dir, name="dnsnet", dns=True)
        resp = api.get("/network/show", params={"name": "dnsnet"})
        assert resp.status_code == 200
        assert resp.json()["dns"] is True

    def test_returned_dns_flag_matches_stored_false(self, api, server_dir):
        seed_network(server_dir, name="nodnsnet", dns=False)
        resp = api.get("/network/show", params={"name": "nodnsnet"})
        assert resp.status_code == 200
        assert resp.json()["dns"] is False

    def test_returned_hosts_dict_matches_stored(self, api, server_dir):
        """A network with no hosts must return an empty hosts dict."""
        seed_network(server_dir, name="emptynet")
        resp = api.get("/network/show", params={"name": "emptynet"})
        assert resp.status_code == 200
        assert resp.json()["hosts"] == {}

    def test_returns_404_for_unknown_network(self, api, server_dir):
        resp = api.get("/network/show", params={"name": "doesnotexist"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /network/lighthouses
# ---------------------------------------------------------------------------

def _seed_lighthouse(server_dir: Path, *, network_name: str = "testnet", host_name: str, public_ip: str) -> None:
    """Add a lighthouse host directly to the DB."""
    store = load_db()
    store.networks[network_name].hosts[host_name] = HostRecord(
        name=host_name,
        ip=ipaddress.ip_address("fd12:3456:789a:1::1"),
        groups=[],
        is_lighthouse=True,
        public_ip=ipaddress.ip_address(public_ip),
    )
    save_db(store)


def _seed_node(server_dir: Path, *, network_name: str = "testnet", host_name: str) -> None:
    """Add a non-lighthouse host directly to the DB."""
    store = load_db()
    store.networks[network_name].hosts[host_name] = HostRecord(
        name=host_name,
        ip=ipaddress.ip_address("fd12:3456:789a:1::2"),
        groups=[],
        is_lighthouse=False,
        public_ip=None,
    )
    save_db(store)


class TestNetworkLighthouses:
    def test_empty_when_no_lighthouses(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_node(server_dir, host_name="node1")

        resp = api.get("/network/lighthouses", params={"network_name": "testnet"})

        assert resp.status_code == 200
        assert resp.json() == {}

    def test_ipv4_lighthouse_formatted_as_ip_colon_4242(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_lighthouse(server_dir, host_name="lh1", public_ip="1.2.3.4")

        resp = api.get("/network/lighthouses", params={"network_name": "testnet"})

        assert resp.status_code == 200
        mapping = resp.json()
        assert len(mapping) == 1
        assert list(mapping.values())[0] == "1.2.3.4:4242"

    def test_ipv6_lighthouse_formatted_with_brackets(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_lighthouse(server_dir, host_name="lh1", public_ip="2001:db8::1")

        resp = api.get("/network/lighthouses", params={"network_name": "testnet"})

        assert resp.status_code == 200
        mapping = resp.json()
        assert list(mapping.values())[0] == "[2001:db8::1]:4242"

    def test_non_lighthouses_excluded_from_mapping(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_lighthouse(server_dir, host_name="lh1", public_ip="1.2.3.4")
        _seed_node(server_dir, host_name="node1")

        resp = api.get("/network/lighthouses", params={"network_name": "testnet"})

        assert resp.status_code == 200
        mapping = resp.json()
        assert len(mapping) == 1

    def test_returns_404_for_unknown_network(self, api, server_dir):
        resp = api.get("/network/lighthouses", params={"network_name": "ghost"})
        assert resp.status_code == 404
