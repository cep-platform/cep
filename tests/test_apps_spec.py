"""Tests for the runtime-neutral app spec, flag parsing, presets and resolution."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cep.apps.spec import (
    AppSpec,
    InvalidSpec,
    Mount,
    Port,
    parse_env,
    parse_mount,
    parse_port,
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
