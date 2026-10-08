from __future__ import annotations

from abc import ABC, abstractmethod

import requests

CADDY_SERVER_NAME = "cep"
CADDY_ADMIN_URL = "http://cep-caddy:2019"
REQUEST_TIMEOUT = 10


class ReverseProxy(ABC):
    @staticmethod
    @abstractmethod
    def add_rproxy(hostname: str, destination: str) -> None:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def remove_rproxy(hostname: str) -> None:
        raise NotImplementedError()


class CaddyReverseProxy(ReverseProxy):

    @staticmethod
    def add_rproxy(hostname: str, destination: str) -> None:
        rproxy_entry = CaddyReverseProxy._get_rproxy_config_entry(
                hostname=hostname,
                destination=destination,
                )
        config = CaddyReverseProxy._add_to_config(
                rproxy_entry=rproxy_entry,
                config=CaddyReverseProxy.config(),
                )
        CaddyReverseProxy._update_config(config=config)

    @staticmethod
    def remove_rproxy(hostname: str) -> None:
        config = CaddyReverseProxy._remove_from_config(
                hostname=hostname,
                config=CaddyReverseProxy.config(),
                )
        CaddyReverseProxy._update_config(config=config)

    @staticmethod
    def config() -> dict:
        response = requests.get(
                f"{CADDY_ADMIN_URL}/config",
                timeout=REQUEST_TIMEOUT,
                )

        response.raise_for_status()
        return response.json()

    @staticmethod
    def initialize_caddy_config(name: str = CADDY_SERVER_NAME) -> None:
        init_config = {
                "apps": {
                    "http": {
                        "servers": {
                            name: {
                                "listen": [":80"],
                                "routes": []
                                }
                            }
                        }
                    }
                }
        CaddyReverseProxy._update_config(init_config)

    @staticmethod
    def ensure_initialized(name: str = CADDY_SERVER_NAME) -> bool:
        """
        Install the base caddy config only when the cep server is missing.

        Returns True when the config was written, False when the cep server
        was already present, so appstore restarts never wipe existing routes.
        Raises requests exceptions when caddy is unreachable.
        """
        try:
            config = CaddyReverseProxy.config()
        except requests.exceptions.HTTPError:
            config = {}

        servers = config.get("apps", {}).get("http", {}).get("servers", {})
        if servers.get(name):
            return False

        CaddyReverseProxy.initialize_caddy_config(name)
        return True

    @staticmethod
    def _update_config(config: dict) -> None:
        response = requests.post(
                f"{CADDY_ADMIN_URL}/load",
                headers={"Content-Type": "application/json"},
                json=config,
                timeout=REQUEST_TIMEOUT,
                )

        response.raise_for_status()

    @staticmethod
    def _get_rproxy_config_entry(hostname: str, destination: str) -> dict:
        return {
                "match": [
                    {
                        "host": [hostname]
                        }
                    ],
                "handle": [
                    {
                        "handler": "reverse_proxy",
                        "upstreams": [
                            {
                                "dial": destination
                                }
                            ]
                        }
                    ]
                }

    @staticmethod
    def _add_to_config(
            rproxy_entry: dict,
            config: dict
            ) -> dict:

        config['apps']['http']['servers'][CADDY_SERVER_NAME]['routes'].append(rproxy_entry)
        return config

    @staticmethod
    def _remove_from_config(
            hostname: str,
            config: dict
            ) -> dict:

        routes = config['apps']['http']['servers'][CADDY_SERVER_NAME]['routes']
        config['apps']['http']['servers'][CADDY_SERVER_NAME]['routes'] = [
                rproxy_entry
                for rproxy_entry in routes
                if rproxy_entry['match'][0]['host'][0] != hostname
                ]
        return config