"""
Tests for host router endpoints and the _sign helper.

TODO references:
  server/host.py:30  – /create "test with and without dns make sure saving works as expected"
  server/host.py:68  – /delete (implicit via DNS integration)
  server/host.py:85  – /show "create dummy database and check if the contents match the spec"
  server/host.py:105 – _sign

create:
- Host is persisted in the DB after a successful call
- Host IP is within the network subnet
- Creating with add_dns_record=True calls add_host_to_dns
- Creating with add_dns_record=False does NOT call add_host_to_dns
- Returns 404 for an unknown network
- Returns 409 when the host already exists

delete:
- Removes host from DB
- Calls remove_host_from_dns with the host name
- Returns 404 for an unknown host

show:
- Returns all HostRecord fields exactly as stored
- Returns 404 for unknown network or host

add_host_to_dns / remove_host_from_dns are exercised implicitly
through host create and delete endpoint calls respectively.

_sign:
- Calls nebula-cert sign with the correct arguments
- Writes the public key to a temp file before calling nebula-cert
- Returns a SignedCertificate whose cert_path and ca_cert_path exist

/host/sign (ordering):
- Returns 404 for an unknown network
- Returns 409 when the network CA has not been created yet (network sign first)
"""
from __future__ import annotations

import ipaddress
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from cep.datamodels import (
    CertificateRequest,
    HostRecord,
    NetworkRecord,
    NetworkStore,
)
from cep.server.utils import load_db, save_db
from cep.server.host import _sign
from tests.conftest import seed_network


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_host(
    server_dir: Path,
    *,
    network_name: str = "testnet",
    host_name: str = "lh1",
    is_lighthouse: bool = True,
    public_ip: str = "1.2.3.4",
) -> HostRecord:
    """Add a host to an existing (or new) network in the DB."""
    from cep.server.utils import load_db, save_db

    store = load_db()
    if network_name not in store.networks:
        net = NetworkRecord(
            name=network_name,
            subnet=ipaddress.IPv6Network("fd12:3456:789a:1::/64"),
            hosts={},
            dns=False,
        )
        store.networks[network_name] = net
        (server_dir / network_name).mkdir(exist_ok=True)

    host = HostRecord(
        name=host_name,
        ip=ipaddress.ip_address("fd12:3456:789a:1::1"),
        groups=[],
        is_lighthouse=is_lighthouse,
        public_ip=ipaddress.ip_address(public_ip) if is_lighthouse else None,
    )
    store.networks[network_name].hosts[host_name] = host
    save_db(store)
    return host


# ---------------------------------------------------------------------------
# /host/create
# ---------------------------------------------------------------------------

class TestHostCreate:
    _LIGHTHOUSE_PAYLOAD = {
        "name": "lh1",
        "network_name": "testnet",
        "is_lighthouse": True,
        "public_ip": "1.2.3.4",
        "add_dns_record": False,
    }
    _NODE_PAYLOAD = {
        "name": "node1",
        "network_name": "testnet",
        "is_lighthouse": False,
        "add_dns_record": False,
    }

    def test_host_is_persisted_in_db(self, api, server_dir):
        seed_network(server_dir, name="testnet")

        resp = api.post("/host/create", json=self._LIGHTHOUSE_PAYLOAD)

        assert resp.status_code == 200
        store = load_db()
        assert "lh1" in store.networks["testnet"].hosts

    def test_host_ip_is_within_network_subnet(self, api, server_dir):
        seed_network(server_dir, name="testnet")

        resp = api.post("/host/create", json=self._NODE_PAYLOAD)

        assert resp.status_code == 200
        store = load_db()
        host_ip = store.networks["testnet"].hosts["node1"].ip
        subnet = store.networks["testnet"].subnet
        assert host_ip in subnet

    def test_create_with_dns_calls_add_host_to_dns(self, api, server_dir, monkeypatch):
        seed_network(server_dir, name="testnet")
        dns_calls = []
        monkeypatch.setattr(
            "cep.server.host.add_host_to_dns",
            lambda req: dns_calls.append(req),
        )

        payload = {**self._NODE_PAYLOAD, "add_dns_record": True}
        api.post("/host/create", json=payload)

        assert len(dns_calls) == 1

    def test_create_without_dns_does_not_call_add_host_to_dns(self, api, server_dir, monkeypatch):
        seed_network(server_dir, name="testnet")
        dns_calls = []
        monkeypatch.setattr(
            "cep.server.host.add_host_to_dns",
            lambda req: dns_calls.append(req),
        )

        api.post("/host/create", json=self._NODE_PAYLOAD)  # add_dns_record=False

        assert dns_calls == []

    def test_returns_404_for_unknown_network(self, api, server_dir):
        payload = {**self._NODE_PAYLOAD, "network_name": "ghost"}
        resp = api.post("/host/create", json=payload)
        assert resp.status_code == 404

    def test_returns_409_when_host_already_exists(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        api.post("/host/create", json=self._LIGHTHOUSE_PAYLOAD)

        resp = api.post("/host/create", json=self._LIGHTHOUSE_PAYLOAD)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /host/delete
# ---------------------------------------------------------------------------

class TestHostDelete:
    def test_removes_host_from_db(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir)

        api.delete("/host/delete", params={"network_name": "testnet", "host_name": "lh1"})

        store = load_db()
        assert "lh1" not in store.networks["testnet"].hosts

    def test_remove_host_from_dns_is_called(self, api, server_dir, monkeypatch):
        """remove_host_from_dns must be called with the deleted host's name."""
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir)

        dns_calls = []
        monkeypatch.setattr(
            "cep.server.host.remove_host_from_dns",
            lambda name: dns_calls.append(name),
        )

        api.delete("/host/delete", params={"network_name": "testnet", "host_name": "lh1"})

        assert dns_calls == ["lh1"], (
            f"remove_host_from_dns must be called with 'lh1', got {dns_calls}"
        )

    def test_returns_404_for_unknown_host(self, api, server_dir):
        seed_network(server_dir, name="testnet")

        resp = api.delete("/host/delete", params={"network_name": "testnet", "host_name": "ghost"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /host/show
# ---------------------------------------------------------------------------

class TestHostShow:
    def test_returns_correct_name(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir, host_name="lh1")

        resp = api.get("/host/show", params={"network_name": "testnet", "host_name": "lh1"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "lh1"

    def test_returned_ip_matches_stored(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir, host_name="lh1")

        resp = api.get("/host/show", params={"network_name": "testnet", "host_name": "lh1"})
        assert resp.json()["ip"] == "fd12:3456:789a:1::1"

    def test_returned_is_lighthouse_matches_stored(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir, host_name="lh1", is_lighthouse=True)

        resp = api.get("/host/show", params={"network_name": "testnet", "host_name": "lh1"})
        assert resp.json()["is_lighthouse"] is True

    def test_returned_public_ip_matches_stored(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir, host_name="lh1", public_ip="203.0.113.1")

        resp = api.get("/host/show", params={"network_name": "testnet", "host_name": "lh1"})
        assert resp.json()["public_ip"] == "203.0.113.1"

    def test_returns_404_for_unknown_network(self, api, server_dir):
        resp = api.get("/host/show", params={"network_name": "ghost", "host_name": "lh1"})
        assert resp.status_code == 404

    def test_returns_404_for_unknown_host(self, api, server_dir):
        seed_network(server_dir, name="testnet")
        resp = api.get("/host/show", params={"network_name": "testnet", "host_name": "ghost"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /host/sign (ordering enforcement)
# ---------------------------------------------------------------------------

class TestSignEndpoint:
    def _request(self, network_name: str = "testnet", host_name: str = "node1") -> CertificateRequest:
        return CertificateRequest(
            network_name=network_name,
            host_name=host_name,
            pub_key="-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----",
        )

    def test_returns_404_for_unknown_network(self, api, server_dir):
        resp = api.post("/host/sign", json=self._request(network_name="ghost").model_dump(mode="json"))

        assert resp.status_code == 404

    def test_returns_409_when_ca_not_created_yet(self, api, server_dir):
        """Host signing requires the network CA – 'network sign' must run first."""
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir, host_name="node1")

        resp = api.post("/host/sign", json=self._request().model_dump(mode="json"))

        assert resp.status_code == 409
        assert "network sign" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# _sign (private helper – tested directly)
# ---------------------------------------------------------------------------

class TestSign:
    def _setup(self, server_dir: Path) -> tuple[Path, CertificateRequest]:
        """Seed DB + CA files, return (net_dir, request)."""
        seed_network(server_dir, name="testnet")
        _seed_host(server_dir, host_name="node1")

        net_dir = server_dir / "testnet"
        (net_dir / "ca.crt").write_text("fake-ca-cert")
        (net_dir / "ca.key").write_text("fake-ca-key")

        req = CertificateRequest(
            network_name="testnet",
            host_name="node1",
            pub_key="-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----",
        )
        return net_dir, req

    def test_calls_nebula_cert_with_correct_args(self, server_dir):
        net_dir, req = self._setup(server_dir)

        with patch("cep.server.host.get_executable_path", return_value="/fake/nebula-cert"), \
             patch("cep.server.host.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _sign(req)

        args = mock_run.call_args[0][0]
        assert args[0] == "/fake/nebula-cert"
        assert "sign" in args
        assert "-name" in args
        assert "node1.testnet" in args
        assert "-ip" in args
        # IP must include /64 subnet mask
        ip_idx = args.index("-ip") + 1
        assert args[ip_idx].endswith("/64")

    def test_writes_pub_key_to_temp_file(self, server_dir):
        net_dir, req = self._setup(server_dir)
        written_paths = []

        original_open = open
        def _capturing_open(path, mode="r", **kwargs):
            if "w" in mode and str(path).endswith(".pub"):
                written_paths.append(Path(path))
            return original_open(path, mode, **kwargs)

        with patch("cep.server.host.get_executable_path", return_value="/fake/nebula-cert"), \
             patch("cep.server.host.subprocess.run") as mock_run, \
             patch("builtins.open", side_effect=_capturing_open):
            mock_run.return_value = MagicMock(returncode=0)
            _sign(req)

        assert len(written_paths) == 1, "Expected exactly one .pub file to be written"
        assert written_paths[0].suffix == ".pub"

    def test_returns_signed_certificate_with_paths(self, server_dir):
        net_dir, req = self._setup(server_dir)

        with patch("cep.server.host.get_executable_path", return_value="/fake/nebula-cert"), \
             patch("cep.server.host.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _sign(req)

        assert result.ca_cert_path == net_dir / "ca.crt"
        assert result.cert_path.name == "node1.crt"
