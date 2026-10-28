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
from importlib import resources
from pathlib import Path

import pytest
import yaml

from cep.apps.incus import PROXY_PORT_LABEL, ComposeConfig, Incus


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
# App templates: x-cep proxy data moved to per-service labels
# ---------------------------------------------------------------------------

def load_raw_template(name: str) -> dict:
    with resources.as_file(
        resources.files("cep.apps.app_templates").joinpath(f"{name}.yml")
    ) as path:
        return yaml.safe_load(Path(path).read_text())


class TestAppTemplateLabels:
    def test_templates_load_ootb_into_compose_config(self):
        assert Incus.list_available_apps()

        for name in Incus.list_available_apps():
            config = Incus.get_app_template(name)
            assert config.services, f"{name} has no services"

    def test_x_cep_extension_removed_from_templates(self):
        for name in Incus.list_available_apps():
            assert "x-cep" not in load_raw_template(name)

    def test_proxy_port_label_on_every_service(self):
        for name in Incus.list_available_apps():
            config = Incus.get_app_template(name)
            for service, service_config in config.services.items():
                labels = service_config.get("labels")
                assert labels is not None, f"{name}/{service} has no labels"
                port = labels.get(PROXY_PORT_LABEL)
                assert port is not None, f"{name}/{service} missing {PROXY_PORT_LABEL}"
                assert str(port).isdigit()

    def test_container_name_on_every_service(self):
        for name in Incus.list_available_apps():
            config = Incus.get_app_template(name)
            for service, service_config in config.services.items():
                container_name = service_config.get("container_name")
                assert container_name, f"{name}/{service} has no container_name"
                assert container_name.startswith("cep-app-"), (
                    f"{name}/{service} container_name must follow the "
                    f"cep-app-<name> convention, got '{container_name}'"
                )

    def test_proxy_port_label_survives_deployment(self, deployment_dir: Path):
        app_config = Incus.get_app_template("redis")

        Incus.add_to_deployment("redis", app_config)

        result = ComposeConfig.load(deployment_dir / "redis" / "compose.yml")
        assert result.services["redis"]["labels"][PROXY_PORT_LABEL] == "6379"
