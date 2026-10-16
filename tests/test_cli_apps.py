"""
Tests for the apps CLI commands.

deploy:
- Forwards app name and network name to /apps/deployProxy
- Fails on non-2xx responses (raise_for_status)

targeted-destroy:
- Forwards network name together with every app name to
  /apps/targetedDestroyProxy
- Fails on non-2xx responses

All HTTP is stubbed: the client_proxy in cep.cli.apps is replaced with a
recording fake.
"""
from __future__ import annotations

import httpx
import pytest

from cep.cli.apps import apps_app


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=httpx.Request("POST", "http://testserver"),
                response=httpx.Response(self.status_code),
            )


class _FakeProxyClient:
    def __init__(self):
        self.posts: list[tuple[str, dict]] = []
        self.deletes: list[tuple[str, dict]] = []
        self.response = _FakeResponse()

    def post(self, path: str, params: dict | None = None) -> _FakeResponse:
        self.posts.append((path, params))
        return self.response

    def delete(self, path: str, params: dict | None = None) -> _FakeResponse:
        self.deletes.append((path, params))
        return self.response


@pytest.fixture()
def fake_proxy_client(monkeypatch: pytest.MonkeyPatch) -> _FakeProxyClient:
    stub = _FakeProxyClient()
    monkeypatch.setattr("cep.cli.apps.client_proxy", stub)
    return stub


class TestDeployCommand:
    def test_forwards_app_and_network_names(self, cli_runner, fake_proxy_client):
        result = cli_runner.invoke(apps_app, ["deploy", "redis", "testnet"])

        assert result.exit_code == 0, result.output
        assert fake_proxy_client.posts == [
            ("/deployProxy", {"name": "redis", "network_name": "testnet"})
        ]

    def test_fails_on_non_2xx_response(self, cli_runner, fake_proxy_client):
        fake_proxy_client.response = _FakeResponse(status_code=409)

        result = cli_runner.invoke(apps_app, ["deploy", "redis", "testnet"])

        assert result.exit_code != 0


class TestTargetedDestroyCommand:
    def test_forwards_network_name_for_every_app(self, cli_runner, fake_proxy_client):
        result = cli_runner.invoke(
            apps_app, ["targeted-destroy", "testnet", "redis", "mongo"]
        )

        assert result.exit_code == 0, result.output
        assert fake_proxy_client.deletes == [
            ("/targetedDestroyProxy", {"name": "redis", "network_name": "testnet"}),
            ("/targetedDestroyProxy", {"name": "mongo", "network_name": "testnet"}),
        ]

    def test_fails_on_non_2xx_response(self, cli_runner, fake_proxy_client):
        fake_proxy_client.response = _FakeResponse(status_code=502)

        result = cli_runner.invoke(
            apps_app, ["targeted-destroy", "testnet", "redis"]
        )

        assert result.exit_code != 0