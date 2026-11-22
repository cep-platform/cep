"""Tests for turning deploy requests (preset, image ref, or user compose) into
the compose file incus-compose runs."""
from __future__ import annotations

import pytest

from cep.apps.compose import CEP_NETWORK, adopt_compose, render, routed_service, to_compose
from cep.apps.incus import PROXY_PORT_LABEL
from cep.apps.spec import AppSpec, DeployRequest, InvalidSpec, Mount, Port, list_presets, load_preset


def test_to_compose_renders_a_routed_service_on_the_shared_network():
    compose = to_compose(load_preset("redis"))

    assert compose == {
        "services": {
            "redis": {
                "image": "redis:7-alpine",
                "container_name": "cep-app-redis",
                "networks": ["cep"],
                "labels": {"cep.app": "true", "cep.preset": "redis", PROXY_PORT_LABEL: "6379"},
                "ports": ["6379:6379/tcp"],
                "volumes": ["redis-data:/data"],
                "command": ["redis-server", "--appendonly", "yes"],
                "restart": "unless-stopped",
            }
        },
        "volumes": {"redis-data": {}},
        "networks": {"cep": CEP_NETWORK},
    }


@pytest.mark.parametrize("preset", list_presets())
def test_every_preset_meets_the_routing_contract(preset):
    """caddy dials <container_name>:<proxy port> over the shared external bridge."""
    service = routed_service(to_compose(load_preset(preset)))
    assert service["container_name"].startswith("cep-app-")
    assert service["labels"][PROXY_PORT_LABEL]
    assert "cep" in service["networks"]


def test_to_compose_optional_fields():
    spec = AppSpec(
        name="web",
        image="ghcr.io/foo/web:1",
        env={"K": "V"},
        mounts=[Mount(source="/srv", target="/srv", read_only=True)],
        workdir="/app",
        restart=False,
        privileged=True,
        proxy_port=80,
    )
    compose = to_compose(spec)
    service = compose["services"]["web"]

    assert service["environment"] == {"K": "V"}
    assert service["volumes"] == ["/srv:/srv:ro"]
    assert service["working_dir"] == "/app"
    assert service["restart"] == "no"
    assert service["privileged"] is True
    assert "volumes" not in compose, "bind mounts are not compose volumes"
    assert "cep.preset" not in service["labels"]


def test_to_compose_requires_a_route_port():
    with pytest.raises(InvalidSpec, match="--proxy-port"):
        to_compose(AppSpec(name="web", image="web"))


def test_adopt_single_service_compose():
    name, compose = adopt_compose({"services": {"web": {"image": "nginx"}}}, proxy_port=80)

    assert name == "web"
    assert compose["services"]["web"] == {
        "image": "nginx",
        "container_name": "cep-app-web",
        "networks": ["cep"],
        "labels": {"cep.app": "true", PROXY_PORT_LABEL: "80"},
    }
    assert compose["networks"] == {"cep": CEP_NETWORK}


def test_adopt_keeps_user_choices():
    user = {
        "services": {
            "web": {
                "image": "nginx",
                "container_name": "my-web",
                "labels": ["team=core", f"{PROXY_PORT_LABEL}=80"],
                "networks": {"backend": {}},
            },
        },
        "networks": {"backend": {}},
    }
    name, compose = adopt_compose(user, name="site")
    web = compose["services"]["web"]

    assert name == "site"
    assert web["container_name"] == "my-web"
    assert web["labels"] == {"team": "core", PROXY_PORT_LABEL: "80", "cep.app": "true"}
    assert web["networks"] == {"backend": {}, "cep": {}}
    assert compose["networks"] == {"backend": {}, "cep": CEP_NETWORK}
    assert "cep" not in user["networks"], "the caller's dict must not be mutated"


def test_adopt_multi_service_routes_the_labelled_one():
    name, compose = adopt_compose({
        "services": {
            "db": {"image": "postgres"},
            "app": {"image": "app", "labels": {PROXY_PORT_LABEL: "8000"}},
        },
    })

    assert name == "app"
    assert routed_service(compose)["container_name"] == "cep-app-app"
    assert "container_name" not in compose["services"]["db"]
    assert compose["services"]["db"]["networks"] == ["cep"]


@pytest.mark.parametrize("compose,match", [
    ({}, "no services"),
    ({"services": {"web": {"image": "nginx"}}}, "--proxy-port"),
    ({"services": {"a": {"image": "a"}, "b": {"image": "b"}}}, PROXY_PORT_LABEL),
    ({"services": {
        "a": {"image": "a", "labels": {PROXY_PORT_LABEL: "1"}},
        "b": {"image": "b", "labels": {PROXY_PORT_LABEL: "2"}},
    }}, PROXY_PORT_LABEL),
    ({"services": {"My_Web": {"image": "nginx", "labels": {PROXY_PORT_LABEL: "80"}}}}, "--name"),
])
def test_adopt_rejects(compose, match):
    with pytest.raises(InvalidSpec, match=match):
        adopt_compose(compose)


def test_render_preset_and_image_ref():
    assert render(DeployRequest(target="redis"))[0] == "redis"
    name, compose = render(DeployRequest(target="ghcr.io/foo/bar:1", ports=[Port(host=81, container=80)]))
    assert name == "bar"
    assert compose["services"]["bar"]["image"] == "ghcr.io/foo/bar:1"


def test_render_user_compose():
    req = DeployRequest(compose={"services": {"web": {"image": "nginx"}}}, proxy_port=80)
    assert render(req)[0] == "web"


@pytest.mark.parametrize("req", [
    DeployRequest(),
    DeployRequest(target="redis", compose={"services": {}}),
    DeployRequest(compose={"services": {"web": {"image": "nginx"}}}, ports=[Port(host=1, container=2)]),
])
def test_render_rejects_ambiguous_requests(req):
    with pytest.raises(InvalidSpec):
        render(req)
