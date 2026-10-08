"""
Tests for Docker helper methods.

TODO references:
  apps/docker.py:79  – add_to_deployment_file "validate templates"
  apps/docker.py:94  – update_deployment_file "deployment_config and logging correctness when failing"

add_to_deployment_file:
- Merges services from app config into an empty deployment file
- Merges services from app config into an existing deployment file without removing prior services
- Merges all top-level keys (services, networks, volumes, configs, secrets)

update_deployment_file:
- Removes a named service from the deployment file
- Logs and returns without error when the service is not found
- Other services are preserved when one service is removed
"""
from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

import pytest
import yaml

from cep.apps.docker import PROXY_PORT_LABEL, ComposeConfig, Docker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def deployment_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect DEPLOYMENT_PATH to a temp directory so tests are isolated."""
    path = tmp_path / "compose.yml"
    monkeypatch.setattr("cep.apps.docker.DEPLOYMENT_PATH", path)
    return path


# ---------------------------------------------------------------------------
# Docker.add_to_deployment_file
# ---------------------------------------------------------------------------

class TestAddToDeploymentFile:
    def test_service_written_to_empty_deployment(self, deployment_path: Path):
        app_config = ComposeConfig(services={"redis": {"image": "redis:7"}})

        Docker.add_to_deployment_file(app_config)

        result = ComposeConfig.load(deployment_path)
        assert "redis" in result.services
        assert result.services["redis"]["image"] == "redis:7"

    def test_service_merged_with_existing_services(self, deployment_path: Path):
        existing = ComposeConfig(services={"nginx": {"image": "nginx:latest"}})
        existing.save(deployment_path)

        app_config = ComposeConfig(services={"redis": {"image": "redis:7"}})
        Docker.add_to_deployment_file(app_config)

        result = ComposeConfig.load(deployment_path)
        assert "nginx" in result.services
        assert "redis" in result.services

    def test_all_top_level_keys_merged(self, deployment_path: Path):
        app_config = ComposeConfig(
            services={"svc": {"image": "alpine"}},
            networks={"mynet": {"driver": "bridge"}},
            volumes={"data": {}},
        )

        Docker.add_to_deployment_file(app_config)

        result = ComposeConfig.load(deployment_path)
        assert "svc" in result.services
        assert "mynet" in result.networks
        assert "data" in result.volumes


# ---------------------------------------------------------------------------
# Docker.update_deployment_file
# ---------------------------------------------------------------------------

class TestUpdateDeploymentFile:
    def test_named_service_is_removed(self, deployment_path: Path):
        config = ComposeConfig(services={"redis": {"image": "redis:7"}})
        config.save(deployment_path)

        Docker.update_deployment_file("redis")

        result = ComposeConfig.load(deployment_path)
        assert "redis" not in result.services

    def test_other_services_preserved_after_removal(self, deployment_path: Path):
        config = ComposeConfig(services={
            "redis": {"image": "redis:7"},
            "nginx": {"image": "nginx:latest"},
        })
        config.save(deployment_path)

        Docker.update_deployment_file("redis")

        result = ComposeConfig.load(deployment_path)
        assert "nginx" in result.services

    def test_missing_service_logs_and_does_not_raise(self, deployment_path: Path, caplog):
        config = ComposeConfig(services={"nginx": {"image": "nginx"}})
        config.save(deployment_path)

        with caplog.at_level(logging.INFO, logger="cep.apps.docker"):
            Docker.update_deployment_file("ghost")

        assert "ghost" in caplog.text
        # File must still be intact
        result = ComposeConfig.load(deployment_path)
        assert "nginx" in result.services


# ---------------------------------------------------------------------------
# App templates: x-cep proxy data moved to per-service labels
# ---------------------------------------------------------------------------

def load_raw_template(name: str) -> dict:
    with resources.as_file(
        resources.files("cep.apps.app_templates").joinpath(f"{name}.yml")
    ) as path:
        return yaml.safe_load(Path(path).read_text())


class TestAppTemplateLabels:
    def test_templates_load_ootb_into_compose_config(self):
        assert Docker.list_available_apps()

        for name in Docker.list_available_apps():
            config = Docker.get_app_template(name)
            assert config.services, f"{name} has no services"

    def test_x_cep_extension_removed_from_templates(self):
        for name in Docker.list_available_apps():
            assert "x-cep" not in load_raw_template(name)

    def test_proxy_port_label_on_every_service(self):
        for name in Docker.list_available_apps():
            config = Docker.get_app_template(name)
            for service, service_config in config.services.items():
                labels = service_config.get("labels")
                assert labels is not None, f"{name}/{service} has no labels"
                port = labels.get(PROXY_PORT_LABEL)
                assert port is not None, f"{name}/{service} missing {PROXY_PORT_LABEL}"
                assert str(port).isdigit()

    def test_proxy_port_label_survives_deployment_merge(self, deployment_path: Path):
        app_config = Docker.get_app_template("redis")

        Docker.add_to_deployment_file(app_config)

        result = ComposeConfig.load(deployment_path)
        assert result.services["redis"]["labels"][PROXY_PORT_LABEL] == "6379"
