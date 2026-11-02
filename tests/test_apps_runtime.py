"""Tests for the shared runtime helpers and runtime selection."""
from __future__ import annotations

import pytest

from cep.apps.runtime import CommandFailed, get_runtime, run


def test_run_returns_stdout():
    assert run(["echo", "hi"]) == "hi\n"


def test_run_raises_with_stderr():
    with pytest.raises(CommandFailed, match="boom"):
        run(["sh", "-c", "echo boom >&2; exit 3"])


def test_get_runtime_rejects_unknown(monkeypatch):
    get_runtime.cache_clear()
    monkeypatch.setenv("CEP_APP_RUNTIME", "podman")
    with pytest.raises(ValueError, match="docker"):
        get_runtime()
    get_runtime.cache_clear()


def test_run_missing_binary_is_command_failed():
    with pytest.raises(CommandFailed, match="no-such-binary-xyz"):
        run(["no-such-binary-xyz"])
