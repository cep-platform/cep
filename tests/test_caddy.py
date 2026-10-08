"""
Tests for the Caddy reverse proxy wrapper.

No network access: the requests module inside cep.apps.caddy is replaced
with an in-memory recorder.

Covers:
- _get_rproxy_config_entry shape
- _add_to_config / _remove_from_config manipulate the cep server routes
- add_rproxy / remove_rproxy load the current config and POST the update
- add_rproxy dials the given destination verbatim (no name prefixing)
- initialize_caddy_config posts the base config for the cep server
- ensure_initialized is idempotent: skips when the cep server is present,
  writes when the config is empty / has other servers / errors on GET,
  and raises when caddy is unreachable
"""
from __future__ import annotations

import pytest
import requests

from cep.apps.caddy import (
    CADDY_ADMIN_URL,
    CADDY_SERVER_NAME,
    CaddyReverseProxy,
)


def _base_config() -> dict:
    return {
        "apps": {
            "http": {
                "servers": {
                    CADDY_SERVER_NAME: {
                        "listen": [":80"],
                        "routes": [],
                    }
                }
            }
        }
    }


def _routes(config: dict) -> list:
    return config["apps"]["http"]["servers"][CADDY_SERVER_NAME]["routes"]


class _FakeResponse:
    def __init__(self, json_data: dict | None = None, status_code: int = 200):
        self._json = json_data if json_data is not None else {}
        self.status_code = status_code

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")


class _RequestsRecorder:
    """Stand-in for the requests module inside cep.apps.caddy."""

    exceptions = requests.exceptions

    def __init__(self, get_response=None, get_error=None):
        self.get_response = get_response or _FakeResponse()
        self.get_error = get_error
        self.get_calls = 0
        self.posts: list[tuple[str, dict]] = []

    def get(self, url, timeout=None):
        self.get_calls += 1
        if self.get_error is not None:
            raise self.get_error
        return self.get_response

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, json))
        return _FakeResponse()


# ---------------------------------------------------------------------------
# Pure config helpers
# ---------------------------------------------------------------------------

class TestRproxyConfigEntry:
    def test_entry_shape(self):
        entry = CaddyReverseProxy._get_rproxy_config_entry(
            hostname="redis.cep.testnet",
            destination="cep-app-redis:6379",
        )

        assert entry["match"] == [{"host": ["redis.cep.testnet"]}]
        assert entry["handle"][0]["handler"] == "reverse_proxy"
        assert entry["handle"][0]["upstreams"] == [{"dial": "cep-app-redis:6379"}]


class TestAddRemoveConfig:
    def test_add_appends_entry_to_routes(self):
        config = _base_config()
        entry = CaddyReverseProxy._get_rproxy_config_entry("a.b.c", "x:1")

        CaddyReverseProxy._add_to_config(rproxy_entry=entry, config=config)

        assert _routes(config) == [entry]

    def test_remove_only_drops_matching_hostname(self):
        keep = CaddyReverseProxy._get_rproxy_config_entry("keep.cep.net", "k:1")
        drop = CaddyReverseProxy._get_rproxy_config_entry("drop.cep.net", "d:2")
        config = _base_config()
        _routes(config).extend([keep, drop])

        CaddyReverseProxy._remove_from_config(hostname="drop.cep.net", config=config)

        assert _routes(config) == [keep]


# ---------------------------------------------------------------------------
# add_rproxy / remove_rproxy flows (mocked HTTP)
# ---------------------------------------------------------------------------

class TestRproxyFlows:
    def test_add_rproxy_posts_route_to_load_endpoint(self, monkeypatch):
        recorder = _RequestsRecorder(get_response=_FakeResponse(json_data=_base_config()))
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        CaddyReverseProxy.add_rproxy(
            hostname="redis.cep.testnet",
            destination="cep-app-redis:6379",
        )

        assert recorder.get_calls == 1
        url, posted = recorder.posts[0]
        assert url == f"{CADDY_ADMIN_URL}/load"
        assert len(_routes(posted)) == 1
        assert _routes(posted)[0]["match"] == [{"host": ["redis.cep.testnet"]}]

    def test_add_rproxy_dials_destination_verbatim(self, monkeypatch):
        """Regression: the wrapper must not prefix dial targets with 'cep-app-'."""
        recorder = _RequestsRecorder(get_response=_FakeResponse(json_data=_base_config()))
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        CaddyReverseProxy.add_rproxy(hostname="h", destination="some-container:1234")

        _, posted = recorder.posts[0]
        dial = _routes(posted)[0]["handle"][0]["upstreams"][0]["dial"]
        assert dial == "some-container:1234"

    def test_remove_rproxy_posts_filtered_config(self, monkeypatch):
        config = _base_config()
        _routes(config).extend([
            CaddyReverseProxy._get_rproxy_config_entry("redis.cep.net", "r:1"),
            CaddyReverseProxy._get_rproxy_config_entry("mongo.cep.net", "m:2"),
        ])
        recorder = _RequestsRecorder(get_response=_FakeResponse(json_data=config))
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        CaddyReverseProxy.remove_rproxy(hostname="redis.cep.net")

        _, posted = recorder.posts[0]
        assert [r["match"][0]["host"][0] for r in _routes(posted)] == ["mongo.cep.net"]


# ---------------------------------------------------------------------------
# initialize_caddy_config / ensure_initialized
# ---------------------------------------------------------------------------

class TestInitialize:
    def test_initialize_posts_base_config(self, monkeypatch):
        recorder = _RequestsRecorder()
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        CaddyReverseProxy.initialize_caddy_config()

        url, posted = recorder.posts[0]
        assert url == f"{CADDY_ADMIN_URL}/load"
        server = posted["apps"]["http"]["servers"][CADDY_SERVER_NAME]
        assert server["listen"] == [":80"]
        assert server["routes"] == []


class TestEnsureInitialized:
    def test_skips_when_cep_server_present(self, monkeypatch):
        recorder = _RequestsRecorder(get_response=_FakeResponse(json_data=_base_config()))
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        assert CaddyReverseProxy.ensure_initialized() is False
        assert recorder.posts == []

    def test_writes_when_config_empty(self, monkeypatch):
        recorder = _RequestsRecorder(get_response=_FakeResponse(json_data={}))
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        assert CaddyReverseProxy.ensure_initialized() is True
        assert len(recorder.posts) == 1

    def test_writes_when_only_other_servers_present(self, monkeypatch):
        config = {"apps": {"http": {"servers": {"srv0": {"listen": [":80"]}}}}}
        recorder = _RequestsRecorder(get_response=_FakeResponse(json_data=config))
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        assert CaddyReverseProxy.ensure_initialized() is True
        assert len(recorder.posts) == 1

    def test_writes_when_config_get_errors(self, monkeypatch):
        recorder = _RequestsRecorder(get_response=_FakeResponse(status_code=404))
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        assert CaddyReverseProxy.ensure_initialized() is True
        assert len(recorder.posts) == 1

    def test_raises_when_caddy_unreachable(self, monkeypatch):
        recorder = _RequestsRecorder(
            get_error=requests.exceptions.ConnectionError("caddy down")
        )
        monkeypatch.setattr("cep.apps.caddy.requests", recorder)

        with pytest.raises(requests.exceptions.ConnectionError):
            CaddyReverseProxy.ensure_initialized()
        assert recorder.posts == []