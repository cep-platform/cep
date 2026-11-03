"""
Tests for the apps CLI commands.

deploy:
- Forwards a DeployRequest body (preset/image ref + flag overrides, or a
  compose file) and the network name to /apps/deployProxy
- Unset flags stay unset so they don't override a preset
- Uses a long per-request timeout (deploys poll for minutes server-side)
- Bad flags / unreadable compose files fail locally; nothing is sent
- Fails on non-2xx responses and prints the server's detail

run:
- --log-level flag is forwarded to uvicorn and drives the root logger
  (compose.dev.yml sets it to debug)
- Fails on unknown log levels

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
    def __init__(self, status_code: int = 200, detail: str = "boom"):
        self.status_code = status_code
        self.is_error = status_code >= 400
        self.detail = detail

    def json(self) -> dict:
        return {"detail": self.detail}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=httpx.Request("POST", "http://testserver"),
                response=httpx.Response(self.status_code),
            )


class _FakeProxyClient:
    def __init__(self):
        self.posts: list[tuple[str, dict, dict, float | None]] = []
        self.deletes: list[tuple[str, dict]] = []
        self.response = _FakeResponse()

    def post(
        self,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
        timeout: float | None = None,
    ) -> _FakeResponse:
        self.posts.append((path, params, json, timeout))
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
    def test_forwards_target_and_network_with_long_timeout(
        self, cli_runner, fake_proxy_client
    ):
        from cep.cli.apps import DEPLOY_TIMEOUT

        result = cli_runner.invoke(apps_app, ["deploy", "redis", "testnet"])

        assert result.exit_code == 0, result.output
        assert fake_proxy_client.posts == [
            ("/deployProxy", {"network_name": "testnet"}, {"target": "redis"}, DEPLOY_TIMEOUT)
        ], (
            "unset flags must not be sent (they would override the preset); "
            "deploys poll the appstore job for minutes server-side, so the "
            "default 5s read timeout would abort every deploy"
        )

    def test_forwards_flag_overrides(self, cli_runner, fake_proxy_client):
        result = cli_runner.invoke(apps_app, [
            "deploy", "ghcr.io/foo/web:1", "testnet", "--name", "web",
            "--port", "8080:80", "--env", "A=1", "--volume", "data:/data:ro",
            "--proxy-port", "80", "--privileged",
        ])

        assert result.exit_code == 0, result.output
        assert fake_proxy_client.posts[0][2] == {
            "target": "ghcr.io/foo/web:1",
            "name": "web",
            "ports": [{"host": 8080, "container": 80, "protocol": "tcp"}],
            "env": {"A": "1"},
            "mounts": [{"source": "data", "target": "/data", "read_only": True}],
            "privileged": True,
            "proxy_port": 80,
        }

    def test_sends_a_compose_file_target_as_compose(
        self, cli_runner, fake_proxy_client, tmp_path
    ):
        path = tmp_path / "compose.yml"
        path.write_text("services:\n  web:\n    image: nginx\n")

        result = cli_runner.invoke(
            apps_app, ["deploy", str(path), "testnet", "--proxy-port", "80"]
        )

        assert result.exit_code == 0, result.output
        assert fake_proxy_client.posts[0][2] == {
            "compose": {"services": {"web": {"image": "nginx"}}},
            "proxy_port": 80,
        }

    @pytest.mark.parametrize("args", [
        ["redis", "testnet", "--port", "nope"],
        ["missing.yml", "testnet"],
    ])
    def test_rejects_bad_input_locally(self, cli_runner, fake_proxy_client, args):
        result = cli_runner.invoke(apps_app, ["deploy", *args])

        assert result.exit_code == 1
        assert fake_proxy_client.posts == []

    def test_fails_on_non_2xx_response_with_detail(self, cli_runner, fake_proxy_client):
        fake_proxy_client.response = _FakeResponse(409, "App 'redis' is already deployed")

        result = cli_runner.invoke(apps_app, ["deploy", "redis", "testnet"])

        assert result.exit_code == 1
        assert "already deployed" in result.output


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


@pytest.fixture()
def fake_uvicorn(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture uvicorn.run kwargs without starting a server."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "cep.cli.apps.uvicorn.run", lambda *a, **kw: calls.append({"args": a, **kw})
    )
    return calls


class TestRunCommand:
    def test_log_level_defaults_to_info(self, cli_runner, fake_uvicorn):
        result = cli_runner.invoke(apps_app, ["run"])

        assert result.exit_code == 0, result.output
        assert fake_uvicorn[0]["log_level"] == "info"
        assert fake_uvicorn[0]["log_config"]["root"]["level"] == "INFO"

    def test_forwards_debug_log_level_and_configures_root_logger(
        self, cli_runner, fake_uvicorn
    ):
        result = cli_runner.invoke(apps_app, ["run", "--log-level", "debug"])

        assert result.exit_code == 0, result.output
        assert fake_uvicorn[0]["log_level"] == "debug"
        # App-level logging (e.g. cep.server.apps) goes through the root
        # logger; it must be set so debug lines actually surface.
        assert fake_uvicorn[0]["log_config"]["root"] == {
            "handlers": ["default"],
            "level": "DEBUG",
        }

    def test_rejects_unknown_log_level(self, cli_runner, fake_uvicorn):
        result = cli_runner.invoke(apps_app, ["run", "--log-level", "verbose"])

        assert result.exit_code != 0
        assert "unknown log level 'verbose'" in result.output
        assert fake_uvicorn == []
