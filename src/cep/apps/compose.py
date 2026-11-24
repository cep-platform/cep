"""Turn a deploy request into the compose file incus-compose runs.

Every deploy ends up as compose: presets and image refs are rendered from an
AppSpec, user compose files are adopted as-is plus the routing contract that
cep-main and caddy rely on (see AGENTS.md "Gotchas"):

- exactly one *routed* service carries the PROXY_PORT_LABEL and a container_name,
  caddy dials `<container_name>:<proxy port>`;
- every service joins the shared external `cep` bridge.

That bridge is shared with the cep stack and every network's apps, and its DNS
answers to instance names, service keys (incus-compose writes a record per key)
and network aliases. So cep picks the routed service's name and key, and user
files can't claim names there.
"""
from __future__ import annotations

import copy
import re

from cep.apps.incus import PROXY_PORT_LABEL
from cep.apps.spec import NAME_RE, AppSpec, DeployRequest, InvalidSpec, resolve

CEP_NETWORK = {"name": "cep", "external": True}
APP_LABEL = {"cep.app": "true"}
# Keys that would let a compose network reach an existing bridge or its DNS.
NETWORK_ESCAPES = ("name", "external", "x-incus", "x-incus-compose")


def container_name(app: str) -> str:
    return f"cep-app-{app}"


def to_compose(spec: AppSpec) -> dict:
    if spec.route_port is None:
        raise InvalidSpec(f"app '{spec.name}' publishes no port; pass --proxy-port")

    preset = {"cep.preset": spec.preset} if spec.preset else {}
    key = container_name(spec.name)
    service = {
        "image": spec.image,
        "container_name": key,
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

    compose = {"services": {key: service}}
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


def _reject_claimed_names(compose: dict, routed: str) -> None:
    for key, service in compose["services"].items():
        for field in ("container_name", "extends"):  # extends can import a container_name
            if field in service:
                raise InvalidSpec(f"service '{key}': {field} is not allowed, cep names app containers")

        networks = service.get("networks")
        if isinstance(networks, dict) and any(networks.values()):
            raise InvalidSpec(
                f"service '{key}': networks can't have options (aliases, ipv4_address, ...); "
                "list the network names only"
            )

        # `incus` is the bridge's search domain, so its record would match every name.
        if key != routed and (key.lower().startswith("cep-") or key.lower() == "incus"):
            raise InvalidSpec(f"service name '{key}' is reserved; rename the service")

    for key, definition in (compose.get("networks") or {}).items():
        if key == "cep":  # always replaced with CEP_NETWORK
            continue
        for field in NETWORK_ESCAPES:
            if field in (definition or {}):
                raise InvalidSpec(f"network '{key}': {field} is not allowed, app networks are private")


def _rename_service(services: dict, old: str, new: str) -> dict:
    for service in services.values():
        depends_on = service.get("depends_on")
        if isinstance(depends_on, list):
            service["depends_on"] = [new if d == old else d for d in depends_on]
        elif isinstance(depends_on, dict):
            service["depends_on"] = {new if d == old else d: v for d, v in depends_on.items()}
    return {new if key == old else key: service for key, service in services.items()}


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
    _reject_claimed_names(compose, routed)

    instance = container_name(name)
    for key, service in services.items():
        labels = _labels(service) | APP_LABEL
        if key == routed:
            if proxy_port is not None:
                labels[PROXY_PORT_LABEL] = str(proxy_port)
            service["container_name"] = instance
        service["labels"] = labels

        networks = service.get("networks") or []
        if isinstance(networks, dict):
            networks.setdefault("cep", {})
        elif "cep" not in networks:
            networks = [*networks, "cep"]
        service["networks"] = networks

    compose["services"] = _rename_service(services, routed, instance)
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
