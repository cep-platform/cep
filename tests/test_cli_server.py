"""
Tests for the server CLI command.

run:
- --log-level flag is forwarded to uvicorn and drives the root logger
  (compose.dev.yml sets it to debug)
- Fails on unknown log levels

uvicorn.run is stubbed so no server is started.
"""
from __future__ import annotations

import pytest

# Invoke through the top-level app: `cep server run ...` is how the
# compose command reaches this sub-app.
from cep.cli.main import app as cep_app


@pytest.fixture()
def fake_uvicorn(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture uvicorn.run args without starting a server."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "cep.cli.server.uvicorn.run", lambda *a, **kw: calls.append({"args": a, **kw})
    )
    return calls


class TestServerRunCommand:
    def test_log_level_defaults_to_info(self, cli_runner, fake_uvicorn):
        result = cli_runner.invoke(cep_app, ["server", "run"])

        assert result.exit_code == 0, result.output
        assert fake_uvicorn[0]["log_level"] == "info"
        assert fake_uvicorn[0]["log_config"]["root"]["level"] == "INFO"

    def test_forwards_debug_log_level_and_configures_root_logger(
        self, cli_runner, fake_uvicorn
    ):
        result = cli_runner.invoke(cep_app, ["server", "run", "--log-level", "debug"])

        assert result.exit_code == 0, result.output
        assert fake_uvicorn[0]["log_level"] == "debug"
        # App-level logging (e.g. cep.server.apps) goes through the root
        # logger; it must be set so debug lines actually surface.
        assert fake_uvicorn[0]["log_config"]["root"] == {
            "handlers": ["default"],
            "level": "DEBUG",
        }

    def test_rejects_unknown_log_level(self, cli_runner, fake_uvicorn):
        result = cli_runner.invoke(cep_app, ["server", "run", "--log-level", "verbose"])

        assert result.exit_code != 0
        assert "unknown log level 'verbose'" in result.output
        assert fake_uvicorn == []
