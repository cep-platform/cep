"""Tests for turning deploy requests (preset, image ref, or user compose) into
the compose file incus-compose runs."""
from __future__ import annotations

import pytest

from cep.apps.compose import (
    CEP_NETWORK,
    adopt_compose,
    container_name,
    render,
    routed_service,
    to_compose,
)
from cep.apps.incus import PROXY_PORT_LABEL
from cep.apps.spec import AppSpec, DeployRequest, InvalidSpec, Mount, Port, list_presets, load_preset

def test_service_key_is_the_instance_name():
    """incus-compose publishes service keys as DNS records on the shared bridge."""
    key = container_name("cep-caddy")
    compose = to_compose(AppSpec(name="cep-caddy", image="evil", proxy_port=80))
    assert list(compose["services"]) == [key]

    _, compose = adopt_compose({"services": {"cep-caddy": {"image": "evil"}}}, proxy_port=80)
    assert list(compose["services"]) == [key]


def test_to_compose_renders_a_routed_service_on_the_shared_network():
    compose = to_compose(load_preset("redis"))
    key = container_name("redis")

    assert compose == {
        "services": {
            key: {
                "image": "redis:7-alpine",
                "container_name": key,
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
    service = compose["services"][container_name("web")]

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
    key = container_name("web")

    assert name == "web"
    assert compose["services"][key] == {
        "image": "nginx",
        "container_name": key,
        "networks": ["cep"],
        "labels": {"cep.app": "true", PROXY_PORT_LABEL: "80"},
    }
    assert compose["networks"] == {"cep": CEP_NETWORK}


def test_adopt_keeps_user_choices():
    user = {
        "services": {
            "web": {
                "image": "nginx",
                "labels": ["team=core", f"{PROXY_PORT_LABEL}=80"],
                "networks": {"backend": {}},
            },
        },
        "networks": {"backend": {}},
    }
    name, compose = adopt_compose(user, name="site")
    web = compose["services"][container_name("site")]

    assert name == "site"
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
    assert routed_service(compose)["container_name"] == container_name("app")
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


@pytest.mark.parametrize("depends_on,expected", [
    (["app"], lambda key: [key]),
    ({"app": {"condition": "service_started"}}, lambda key: {key: {"condition": "service_started"}}),
])
def test_adopt_keeps_depends_on_pointing_at_the_renamed_service(depends_on, expected):
    _, compose = adopt_compose({"services": {
        "app": {"image": "app", "labels": {PROXY_PORT_LABEL: "8000"}},
        "worker": {"image": "app", "depends_on": depends_on},
    }})
    assert compose["services"]["worker"]["depends_on"] == expected(container_name("app"))


@pytest.mark.parametrize("field", [
    {"container_name": "cep-caddy"},
    {"extends": {"file": "/elsewhere/compose.yml", "service": "x"}},
    {"networks": {"cep": {"aliases": ["cep-caddy"]}}},
    {"networks": {"cep": {"ipv4_address": "10.0.0.2"}}},
])
@pytest.mark.parametrize("target", ["app", "db"])
def test_adopt_rejects_a_service_claiming_a_name(target, field):
    services = {
        "app": {"image": "app", "labels": {PROXY_PORT_LABEL: "8000"}},
        "db": {"image": "postgres"},
    }
    services[target] |= field
    with pytest.raises(InvalidSpec, match=next(iter(field))):
        adopt_compose({"services": services})


@pytest.mark.parametrize("key", ["cep-caddy", "CEP-main", "cep-app-web-0123", "incus"])
def test_adopt_rejects_reserved_service_names(key):
    """Unrouted services keep their key, and so their DNS record."""
    with pytest.raises(InvalidSpec, match="reserved"):
        adopt_compose({"services": {
            "app": {"image": "app", "labels": {PROXY_PORT_LABEL: "8000"}},
            key: {"image": "evil"},
        }})


@pytest.mark.parametrize("definition", [
    {"name": "cep"},
    {"external": True},
    {"x-incus": {"raw.dnsmasq": "address=/cep-caddy/10.0.0.9"}},
    {"x-incus-compose": {"network": "cep"}},
])
def test_adopt_rejects_a_network_reaching_outside_the_app(definition):
    with pytest.raises(InvalidSpec, match=next(iter(definition))):
        adopt_compose({
            "services": {"app": {"image": "app", "networks": ["side"]}},
            "networks": {"side": definition},
        }, proxy_port=80)


def test_render_preset_and_image_ref():
    assert render(DeployRequest(target="redis"))[0] == "redis"
    name, compose = render(DeployRequest(target="ghcr.io/foo/bar:1", ports=[Port(host=81, container=80)]))
    assert name == "bar"
    assert compose["services"][container_name("bar")]["image"] == "ghcr.io/foo/bar:1"


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
