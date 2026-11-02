"""The container runtime the app store deploys to (Docker today, Incus going forward)."""
from __future__ import annotations

import os
import subprocess
from functools import cache
from typing import Protocol

from cep.apps.spec import AppSpec, AppStatus, InvalidSpec


class UnsupportedSpec(InvalidSpec):
    """The spec is valid, but this runtime cannot honour part of it."""


class CommandFailed(RuntimeError):
    def __init__(self, argv: list[str], stderr: str):
        self.argv = argv
        self.stderr = stderr
        super().__init__(f"{' '.join(argv)} failed: {stderr.strip()}")


def run(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CommandFailed(argv, proc.stderr)
    return proc.stdout


class Runtime(Protocol):
    def deploy(self, spec: AppSpec) -> None: ...
    def destroy(self, name: str) -> None: ...
    def list(self) -> list[AppStatus]: ...


@cache
def get_runtime() -> Runtime:
    """The runtime selected by CEP_APP_RUNTIME (docker | incus, default docker)."""
    kind = os.environ.get("CEP_APP_RUNTIME", "docker")
    if kind == "docker":
        from cep.apps.runtime.docker import DockerRuntime

        return DockerRuntime()
    if kind == "incus":
        from cep.apps.runtime.incus import IncusRuntime

        return IncusRuntime()
    raise ValueError(f"CEP_APP_RUNTIME must be 'docker' or 'incus', got '{kind}'")
