"""
Tests for the network CLI commands.

create:
- POSTs the name and dns flag as JSON to /network/create
- Prints the server's detail and exits non-zero on 409 (duplicate network)
- Exits non-zero on other non-2xx responses

All HTTP is stubbed: the client in cep.cli.network is replaced with a
recording fake.
"""
from __future__ import annotations

import httpx
import pytest

from cep.cli.network import network_app


class _FakeResponse:
    def __init__(self, status_code: int = 200, detail: str = ""):
        self.status_code = status_code
        self._detail = detail

    def json(self) -> dict:
        return {"detail": self._detail}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=httpx.Request("POST", "http://testserver"),
                response=httpx.Response(self.status_code),
            )


class _FakeNetworkClient:
    def __init__(self):
        self.posts: list[tuple[str, dict]] = []
        self.response = _FakeResponse()

    def post(self, path: str, json: dict | None = None) -> _FakeResponse:
        self.posts.append((path, json))
        return self.response


@pytest.fixture()
def fake_network_client(monkeypatch: pytest.MonkeyPatch) -> _FakeNetworkClient:
    stub = _FakeNetworkClient()
    monkeypatch.setattr("cep.cli.network.client", stub)
    return stub


class TestCreateCommand:
    def test_posts_name_and_dns_as_json(self, cli_runner, fake_network_client):
        result = cli_runner.invoke(network_app, ["create", "testnet"])

        assert result.exit_code == 0, result.output
        assert fake_network_client.posts == [
            ("/create", {"name": "testnet", "dns": True})
        ]

    def test_no_dns_flag(self, cli_runner, fake_network_client):
        result = cli_runner.invoke(network_app, ["create", "testnet", "--no-dns"])

        assert result.exit_code == 0, result.output
        assert fake_network_client.posts == [
            ("/create", {"name": "testnet", "dns": False})
        ]

    def test_conflict_prints_detail_and_exits_nonzero(self, cli_runner, fake_network_client):
        fake_network_client.response = _FakeResponse(
            status_code=409, detail="Network 'testnet' already exists"
        )

        result = cli_runner.invoke(network_app, ["create", "testnet"])

        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_fails_on_other_errors(self, cli_runner, fake_network_client):
        fake_network_client.response = _FakeResponse(status_code=500)

        result = cli_runner.invoke(network_app, ["create", "testnet"])

        assert result.exit_code != 0
