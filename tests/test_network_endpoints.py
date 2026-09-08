"""
Tests for the /network/create, /network/sign, /network/delete, /network/show, and /network/lighthouses router endpoints.

TODO references:
  server/network.py:73  – "make sure network_record deletion is tested"
  server/network.py:100 – "create dummy database and check if the contents match the spec"
  server/network.py:117 – "test lighthouses implicitly in an integration test"

create:
- Persists the network record in the DB
- Does NOT create a CA (CA creation moved to /network/sign)

sign:
- Creates ca.crt/ca.key in the network directory
- Returns 404 when the network does not exist (ordering: create before sign)
- Returns 409 when a CA already exists for the network

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
"""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import pytest

from cep.datamodels import HostRecord, NetworkRecord, NetworkStore
from cep.server.utils import load_db, save_db
from tests.conftest import seed_network


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
# /network/create
# ---------------------------------------------------------------------------

class TestNetworkCreate:
    def test_persists_network_record(self, api, server_dir):
        resp = api.get("/network/create", params={"name": "freshnet", "dns": False})

        assert resp.status_code == 200
        store = load_db()
        assert "freshnet" in store.networks
        assert resp.json()["name"] == "freshnet"

    def test_does_not_create_ca(self, api, server_dir):
        """CA creation is a separate step (network sign) and must not happen here."""
        api.get("/network/create", params={"name": "freshnet", "dns": False})

        assert not (server_dir / "freshnet" / "ca.crt").exists()
        assert not (server_dir / "freshnet" / "ca.key").exists()


# ---------------------------------------------------------------------------
# /network/sign
# ---------------------------------------------------------------------------

class TestNetworkSign:
    def test_creates_ca_files_in_network_dir(self, api, server_dir):
        seed_network(server_dir, name="mynet")

        resp = api.get("/network/sign", params={"name": "mynet"})

        assert resp.status_code == 200
        assert (server_dir / "mynet" / "ca.crt").exists()
        assert (server_dir / "mynet" / "ca.key").exists()

    def test_returns_404_for_unknown_network(self, api, server_dir):
        resp = api.get("/network/sign", params={"name": "ghost"})

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_returns_409_when_ca_already_exists(self, api, server_dir):
        seed_network(server_dir, name="mynet")
        (server_dir / "mynet" / "ca.crt").write_text("existing")

        resp = api.get("/network/sign", params={"name": "mynet"})

        assert resp.status_code == 409

    def test_returns_409_when_only_key_exists(self, api, server_dir):
        seed_network(server_dir, name="mynet")
        (server_dir / "mynet" / "ca.key").write_text("existing")

        resp = api.get("/network/sign", params={"name": "mynet"})

        assert resp.status_code == 409


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
