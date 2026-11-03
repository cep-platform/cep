"""Tests for the app spec, flag parsing, presets and resolution."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cep.apps.spec import (
    AppSpec,
    DeployRequest,
    InvalidSpec,
    Mount,
    Port,
    default_name,
    list_presets,
    load_preset,
    parse_env,
    parse_mount,
    parse_port,
    resolve,
)


def test_parse_port():
    assert parse_port("8080:80") == Port(host=8080, container=80, protocol="tcp")
    assert parse_port("53:53/udp") == Port(host=53, container=53, protocol="udp")


@pytest.mark.parametrize("bad", ["80", "a:b", "1:2/sctp", ""])
def test_parse_port_rejects(bad):
    with pytest.raises(InvalidSpec):
        parse_port(bad)


def test_parse_mount():
    assert parse_mount("/srv/x:/data") == Mount(source="/srv/x", target="/data")
    assert parse_mount("pgdata:/var/lib/pg:ro") == Mount(
        source="pgdata", target="/var/lib/pg", read_only=True
    )
    assert parse_mount("pgdata:/x").is_volume
    assert not parse_mount("/a:/x").is_volume


@pytest.mark.parametrize("bad", ["./app:/app", "~/x:/x", "a/b:/x", "/a", "/a:/b:rw"])
def test_parse_mount_rejects(bad):
    with pytest.raises(InvalidSpec):
        parse_mount(bad)


def test_parse_env():
    assert parse_env("K=a=b") == ("K", "a=b")
    with pytest.raises(InvalidSpec):
        parse_env("novalue")


@pytest.mark.parametrize("bad", ["Redis", "1abc", "my_app", ""])
def test_appspec_rejects_bad_names(bad):
    with pytest.raises(ValidationError):
        AppSpec(name=bad, image="redis")


def test_every_preset_loads():
    assert list_presets() == ["mongo", "navidrome", "nginx", "postgres", "python", "redis"]
    for p in list_presets():
        assert load_preset(p).preset == p


@pytest.mark.parametrize("ref,name", [
    ("redis", "redis"),
    ("redis:7-alpine", "redis"),
    ("ghcr.io/foo/bar:1.0", "bar"),
    ("localhost:5000/foo/baz", "baz"),
    ("nginx@sha256:abc", "nginx"),
])
def test_default_name(ref, name):
    assert default_name(ref) == name


@pytest.mark.parametrize("ref", ["UPPER:1", "ghcr.io/foo/my_app"])
def test_default_name_requires_explicit_name(ref):
    with pytest.raises(InvalidSpec, match="--name"):
        default_name(ref)


def test_resolve_image_ref():
    spec = resolve(DeployRequest(target="redis:7", ports=[Port(host=1, container=2)]))
    assert (spec.name, spec.image, spec.preset, spec.ports) == (
        "redis", "redis:7", None, [Port(host=1, container=2)]
    )


def test_resolve_explicit_name_skips_derivation():
    assert resolve(DeployRequest(target="ghcr.io/foo/my_app", name="app")).name == "app"


def test_resolve_preset_env_merges_and_keeps_rest():
    base = load_preset("postgres")
    spec = resolve(DeployRequest(target="postgres", env={"POSTGRES_PASSWORD": "x"}))
    assert spec.env == {**base.env, "POSTGRES_PASSWORD": "x"}
    assert spec.ports == base.ports and spec.mounts == base.mounts
    assert spec.preset == "postgres"


def test_resolve_preset_ports_replace():
    assert resolve(DeployRequest(target="redis", ports=[])).ports == []


def test_resolve_full_ref_bypasses_preset():
    assert resolve(DeployRequest(target="docker.io/library/redis")).preset is None


def test_route_port_defaults_to_first_container_port():
    spec = AppSpec(name="a", image="i", ports=[Port(host=8080, container=80), Port(host=1, container=2)])
    assert spec.route_port == 80


def test_route_port_prefers_proxy_port():
    spec = AppSpec(name="a", image="i", ports=[Port(host=8080, container=80)], proxy_port=9000)
    assert spec.route_port == 9000
    assert AppSpec(name="a", image="i").route_port is None


def test_resolve_proxy_port_override():
    assert resolve(DeployRequest(target="redis", proxy_port=1234)).route_port == 1234


def test_resolve_bad_override_name_is_invalid_spec():
    with pytest.raises(InvalidSpec):
        resolve(DeployRequest(target="redis", name="Bad_Name"))
