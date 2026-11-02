"""Runtime-neutral description of an app, and how users and presets produce one."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

NAME_RE = r"^[a-z][a-z0-9-]{0,62}$"
VOLUME_NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
INCUS_NATIVE_REMOTES = frozenset({"images", "ubuntu", "ubuntu-daily"})
KNOWN_REMOTE_PREFIXES = INCUS_NATIVE_REMOTES | {"docker"}


class InvalidSpec(ValueError):
    """The requested app cannot be described or run as asked (maps to HTTP 422)."""


class Port(BaseModel):
    host: int
    container: int
    protocol: Literal["tcp", "udp"] = "tcp"


class Mount(BaseModel):
    source: str  # absolute path on the runtime's host, or a bare volume name
    target: str
    read_only: bool = False

    @field_validator("source")
    @classmethod
    def _absolute_or_volume(cls, v: str) -> str:
        if v.startswith("/") or re.match(VOLUME_NAME_RE, v):
            return v
        raise ValueError(f"mount source '{v}' must be an absolute path or a volume name")

    @property
    def is_volume(self) -> bool:
        return not self.source.startswith("/")


class AppSpec(BaseModel):
    name: str
    image: str  # raw ref, interpreted by the runtime
    ports: list[Port] = []
    env: dict[str, str] = {}
    mounts: list[Mount] = []
    command: list[str] | None = None
    workdir: str | None = None
    restart: bool = True
    privileged: bool = False
    preset: str | None = None  # set by preset resolution, not by users

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not re.match(NAME_RE, v):
            raise ValueError(f"app name '{v}' must match {NAME_RE}")
        return v


class AppStatus(BaseModel):
    name: str
    image: str
    state: str
    preset: str | None = None


def parse_port(s: str) -> Port:
    """`HOST:CONTAINER[/tcp|udp]`"""
    ports, _, protocol = s.partition("/")
    host, sep, container = ports.partition(":")
    try:
        if not sep:
            raise ValueError
        return Port(host=host, container=container, protocol=protocol or "tcp")
    except (ValueError, ValidationError):
        raise InvalidSpec(f"invalid port '{s}', expected HOST:CONTAINER[/tcp|udp]") from None


def parse_mount(s: str) -> Mount:
    """`SOURCE:TARGET[:ro]`"""
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return Mount(source=parts[0], target=parts[1])
        if len(parts) == 3 and parts[2] == "ro":
            return Mount(source=parts[0], target=parts[1], read_only=True)
        raise ValueError
    except (ValueError, ValidationError):
        raise InvalidSpec(
            f"invalid volume '{s}', expected SOURCE:TARGET[:ro] with an absolute "
            "SOURCE path or a volume name"
        ) from None


def parse_env(s: str) -> tuple[str, str]:
    """`KEY=VALUE`"""
    key, sep, value = s.partition("=")
    if not sep or not key:
        raise InvalidSpec(f"invalid env '{s}', expected KEY=VALUE")
    return key, value
