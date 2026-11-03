"""
Tests for Incus helper methods.

TODO references:
  incus.py:86  – add_to_deployment "validate templates"
  incus.py:94  – remove_from_deployment "validate templates"

add_to_deployment:
- Writes the app config to DEPLOYMENT_DIR/<app_id>/compose.yml
- Deployments of separate apps are isolated from each other
- Persists all top-level keys (services, networks, volumes, configs, secrets)

remove_from_deployment:
- Removes an app's deployment directory
- Other apps are preserved when one app is removed
- Logs and returns without error when no deployment directory exists
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from cep.apps.compose import render
from cep.apps.incus import PROXY_PORT_LABEL, ComposeConfig, Incus
from cep.apps.spec import DeployRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def deployment_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect DEPLOYMENT_DIR to a temp directory so tests are isolated."""
    path = tmp_path / "deployments"
    path.mkdir()
    monkeypatch.setattr("cep.apps.incus.DEPLOYMENT_DIR", path)
    return path


# ---------------------------------------------------------------------------
# Incus.add_to_deployment
# ---------------------------------------------------------------------------

class TestAddToDeployment:
    def test_app_config_written_to_deployment_file(self, deployment_dir: Path):
        app_config = ComposeConfig(services={"redis": {"image": "redis:7"}})

        Incus.add_to_deployment("redis", app_config)

        result = ComposeConfig.load(deployment_dir / "redis" / "compose.yml")
        assert "redis" in result.services
        assert result.services["redis"]["image"] == "redis:7"

    def test_deployments_of_separate_apps_are_isolated(self, deployment_dir: Path):
        first = ComposeConfig(services={"nginx": {"image": "nginx:latest"}})
        second = ComposeConfig(services={"redis": {"image": "redis:7"}})

        Incus.add_to_deployment("nginx", first)
        Incus.add_to_deployment("redis", second)

        first_result = ComposeConfig.load(deployment_dir / "nginx" / "compose.yml")
        second_result = ComposeConfig.load(deployment_dir / "redis" / "compose.yml")
        assert "nginx" in first_result.services
        assert "redis" in second_result.services
        assert "nginx" not in second_result.services

    def test_all_top_level_keys_persisted(self, deployment_dir: Path):
        app_config = ComposeConfig(
            services={"svc": {"image": "alpine"}},
            networks={"mynet": {"driver": "bridge"}},
            volumes={"data": {}},
        )

        Incus.add_to_deployment("svc", app_config)

        result = ComposeConfig.load(deployment_dir / "svc" / "compose.yml")
        assert "svc" in result.services
        assert "mynet" in result.networks
        assert "data" in result.volumes


# ---------------------------------------------------------------------------
# Incus.remove_from_deployment
# ---------------------------------------------------------------------------

class TestRemoveFromDeployment:
    def test_app_deployment_dir_is_removed(self, deployment_dir: Path):
        config = ComposeConfig(services={"redis": {"image": "redis:7"}})
        Incus.add_to_deployment("redis", config)

        Incus.remove_from_deployment("redis")

        assert not (deployment_dir / "redis" / "compose.yml").exists()

    def test_other_apps_preserved_after_removal(self, deployment_dir: Path):
        Incus.add_to_deployment(
            "redis", ComposeConfig(services={"redis": {"image": "redis:7"}})
        )
        Incus.add_to_deployment(
            "nginx", ComposeConfig(services={"nginx": {"image": "nginx:latest"}})
        )

        Incus.remove_from_deployment("redis")

        assert not (deployment_dir / "redis").exists()
        result = ComposeConfig.load(deployment_dir / "nginx" / "compose.yml")
        assert "nginx" in result.services

    def test_missing_deployment_logs_and_does_not_raise(
        self, deployment_dir: Path, caplog
    ):
        with caplog.at_level(logging.INFO, logger="cep.apps.incus"):
            Incus.remove_from_deployment("ghost")

        assert "ghost" in caplog.text


# ---------------------------------------------------------------------------
# Rendered apps reach incus-compose intact
# ---------------------------------------------------------------------------

class TestRenderedAppDeployment:
    """The routing contract (proxy-port label, container_name, external `cep`
    bridge; see cep.apps.compose) must survive the write to the file
    incus-compose runs: a non-external network would give every app its own
    isolated <project>-cep bridge and caddy would answer 502."""

    def test_routing_contract_survives_deployment(self, deployment_dir: Path):
        name, compose = render(DeployRequest(target="navidrome"))

        Incus.add_to_deployment(name, ComposeConfig(**compose))

        result = ComposeConfig.load(deployment_dir / name / "compose.yml")
        service = result.services["navidrome"]
        assert service["labels"][PROXY_PORT_LABEL] == "4533"
        assert service["container_name"] == "cep-app-navidrome"
        assert result.networks["cep"] == {"name": "cep", "external": True}
