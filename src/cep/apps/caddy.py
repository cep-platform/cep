from __future__ import annotations

import requests
from abc import ABC, abstractmethod


class ReverseProxy(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def add_rproxy(hostname: str, destination: str):
        raise NotImplementedError()

    @abstractmethod
    def remove_rproxy(hostname: str):
        raise NotImplementedError()


class CaddyReverseProxy(ReverseProxy):

    @staticmethod
    def add_rproxy(hostname: str, destination: str):
        rproxy_entry = CaddyReverseProxy._get_rproxy_config_entry(
                hostname=hostname,
                destination=destination,
                )
        config = CaddyReverseProxy._add_to_config(
                rproxy_entry=rproxy_entry,
                config= CaddyReverseProxy.config,
                )
        CaddyReverseProxy._update_config(config=config)

    def remove_rproxy(hostname: str):
        config = CaddyReverseProxy._remove_from_config(
                hostname=hostname,
                config=CaddyReverseProxy.config,
                )
        CaddyReverseProxy._update_config(config=config)

    @property
    def config() -> dict:
        response = requests.get("http://caddy:2019/config")

        response.raise_for_status()
        return response.json()

    def initialize_caddy_config(name: str = "cep"):
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

    def _update_config(config: dict):
        response = requests.post(
                "http://caddy:2019/load",
                headers={"Content-Type": "application/json"},
                json=config,
                )

        response.raise_for_status()

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

    def _add_to_config(
            rproxy_entry: dict,
            config: dict
            ) -> dict:

        config['apps']['http']['servers']['cep']['routes'].append(rproxy_entry)
        return config

    def _remove_from_config(
            hostname: str,
            config: dict
            ) -> dict:

        routes = config['apps']['http']['servers']['cep']['routes']
        updated_routes = [
                rproxy_entry
                for rproxy_entry in routes
                if rproxy_entry['match'][0]['host'][0] != hostname
                ]
        config['apps']['http']['servers']['cep']['routes'] = updated_routes
        return config

