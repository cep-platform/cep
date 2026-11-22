"""Turn a deploy request into the compose file incus-compose runs.

Every deploy ends up as compose: presets and image refs are rendered from an
AppSpec, user compose files are adopted as-is plus the routing contract that
cep-main and caddy rely on (see AGENTS.md "Gotchas"):

- exactly one *routed* service carries the PROXY_PORT_LABEL and a container_name,
  caddy dials `<container_name>:<proxy port>`;
- every service joins the shared external `cep` bridge.
"""
from __future__ import annotations

import copy
import re

from cep.apps.incus import PROXY_PORT_LABEL
from cep.apps.spec import NAME_RE, AppSpec, DeployRequest, InvalidSpec, resolve

CEP_NETWORK = {"name": "cep", "external": True}
APP_LABEL = {"cep.app": "true"}


def container_name(app: str) -> str:
    return f"cep-app-{app}"


def to_compose(spec: AppSpec) -> dict:
    if spec.route_port is None:
        raise InvalidSpec(f"app '{spec.name}' publishes no port; pass --proxy-port")

    preset = {"cep.preset": spec.preset} if spec.preset else {}
    service = {
        "image": spec.image,
        "container_name": container_name(spec.name),
        "networks": ["cep"],
        "labels": {**APP_LABEL, **preset, PROXY_PORT_LABEL: str(spec.route_port)},
    }
    optional = {
        "ports": [f"{p.host}:{p.container}/{p.protocol}" for p in spec.ports],
        "environment": spec.env,
        "volumes": [f"{m.source}:{m.target}" + (":ro" if m.read_only else "") for m in spec.mounts],
        "command": spec.command,
        "working_dir": spec.workdir,
        "privileged": spec.privileged or None,
    }
    service |= {k: v for k, v in optional.items() if v}
    service["restart"] = "unless-stopped" if spec.restart else "no"

    compose = {"services": {spec.name: service}}
    if volumes := sorted({m.source for m in spec.mounts if m.is_volume}):
        compose["volumes"] = {v: {} for v in volumes}
    compose["networks"] = {"cep": CEP_NETWORK}
    return compose


def _labels(service: dict) -> dict:
    """Compose allows labels as a map or a `KEY=VALUE` list; normalise to a map."""
    labels = service.get("labels") or {}
    if isinstance(labels, list):
        labels = dict(item.split("=", 1) if "=" in item else (item, "") for item in labels)
    return labels


def _routed(services: dict, proxy_port: int | None) -> str:
    labelled = [k for k, s in services.items() if PROXY_PORT_LABEL in _labels(s)]
    if len(services) == 1:
        if labelled or proxy_port is not None:
            return next(iter(services))
        raise InvalidSpec(f"label the service with '{PROXY_PORT_LABEL}' or pass --proxy-port")
    if len(labelled) != 1:
        raise InvalidSpec(
            f"exactly one service must carry the '{PROXY_PORT_LABEL}' label, got {len(labelled)}"
        )
    return labelled[0]


def routed_service(compose: dict) -> dict:
    """The service the reverse proxy routes to."""
    services = compose.get("services") or {}
    return services[_routed(services, None)]


def adopt_compose(compose: dict, name: str | None = None, proxy_port: int | None = None) -> tuple[str, dict]:
    """Apply the routing contract to a user compose file. Returns (app name, compose)."""
    compose = copy.deepcopy(compose)
    services = compose.get("services") or {}
    if not services:
        raise InvalidSpec("compose file defines no services")

    routed = _routed(services, proxy_port)
    name = name or routed
    if not re.match(NAME_RE, name):
        raise InvalidSpec(f"app name '{name}' must match {NAME_RE}; pass --name")

    for key, service in services.items():
        labels = _labels(service) | APP_LABEL
        if key == routed:
            if proxy_port is not None:
                labels[PROXY_PORT_LABEL] = str(proxy_port)
            service.setdefault("container_name", container_name(name))
        service["labels"] = labels

        networks = service.get("networks") or []
        if isinstance(networks, dict):
            networks.setdefault("cep", {})
        elif "cep" not in networks:
            networks = [*networks, "cep"]
        service["networks"] = networks

    compose["networks"] = {**(compose.get("networks") or {}), "cep": CEP_NETWORK}
    return name, compose


def render(req: DeployRequest) -> tuple[str, dict]:
    """The app name and the compose file to deploy for `req`."""
    if (req.target is None) == (req.compose is None):
        raise InvalidSpec("deploy needs exactly one of a target (preset or image ref) or a compose file")

    if req.compose is not None:
        overrides = req.model_dump(include={"ports", "env", "mounts", "privileged"}, exclude_none=True)
        if overrides:
            raise InvalidSpec(
                f"{', '.join(sorted(overrides))} cannot be combined with a compose file; edit the file instead"
            )
        return adopt_compose(req.compose, req.name, req.proxy_port)

    spec = resolve(req)
    return spec.name, to_compose(spec)
