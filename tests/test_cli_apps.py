"""Tests for turning `cep apps deploy` flags into a DeployRequest."""
from __future__ import annotations

import pytest

from cep.apps.spec import DeployRequest, InvalidSpec, Mount, Port
from cep.cli.apps import build_deploy_request


def test_build_deploy_request_flags():
    req = build_deploy_request("redis", None, ["6380:6379"], ["A=1"], ["v:/d:ro"], False)
    assert req == DeployRequest(
        target="redis", ports=[Port(host=6380, container=6379)], env={"A": "1"},
        mounts=[Mount(source="v", target="/d", read_only=True)],
    )


def test_build_deploy_request_no_flags_overrides_nothing():
    req = build_deploy_request("redis", None, [], [], [], False)
    assert req.model_dump(exclude_none=True) == {"target": "redis"}


def test_build_deploy_request_bad_flag():
    with pytest.raises(InvalidSpec):
        build_deploy_request("redis", None, ["nope"], [], [], False)


def test_app_clients_allow_slow_image_pulls():
    """Deploy blocks until the image is pulled; httpx's 5s default would cut it off."""
    from cep.cli.apps import client_proxy
    from cep.server.apps import client as server_proxy_client

    assert client_proxy.timeout.read >= 600
    assert server_proxy_client.timeout.read >= 600
