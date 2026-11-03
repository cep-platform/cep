"""
Tests for generate_ula_prefix and create_ca.

TODO references:
  server/network.py:25 – "last 64 bits needs to be zero valued, needs to return valid IPv6"
  server/network.py:32 – create_ca

generate_ula_prefix:
- Returns an IPv6Network with prefix length /64
- First byte is 0xfd (Unique Local Address)
- Network address has the last 64 bits zeroed (host part is zero)
- Is globally unique – two consecutive calls produce different prefixes

create_ca:
- Invokes nebula-cert with explicit -out-crt/-out-key paths inside ca_dir
- Passes check=True so nebula-cert failures raise
- Writes certs to the explicit paths; stale ca.* files in cwd are ignored
- Raises 500 (with nebula-cert stderr) when CA creation fails
- Returns ca_dir
"""
from __future__ import annotations

import ipaddress
import subprocess
from pathlib import Path
from unittest.mock import call, patch, MagicMock

import pytest
from fastapi import HTTPException

from cep.server.network import generate_ula_prefix, create_ca


class TestGenerateUlaPrefix:
    def test_returns_ipv6_network(self):
        result = generate_ula_prefix()
        assert isinstance(result, ipaddress.IPv6Network)

    def test_prefix_length_is_64(self):
        result = generate_ula_prefix()
        assert result.prefixlen == 64, f"Expected /64 but got /{result.prefixlen}"

    def test_first_byte_is_fd(self):
        """ULA addresses must start with 0xfd (fc00::/7 with L-bit set)."""
        result = generate_ula_prefix()
        first_byte = int(result.network_address) >> 120
        assert first_byte == 0xfd, f"Expected first byte 0xfd, got 0x{first_byte:02x}"

    def test_last_64_bits_of_network_address_are_zero(self):
        """
        The host part of the network address must be all zeros –
        only the upper 64 bits (the prefix) should be non-zero.
        """
        result = generate_ula_prefix()
        network_int = int(result.network_address)
        last_64 = network_int & ((1 << 64) - 1)
        assert last_64 == 0, (
            f"Expected lower 64 bits to be 0, got {last_64:#x}"
        )

    def test_uniqueness_across_calls(self):
        """Two independent calls should (with overwhelming probability) differ."""
        results = {generate_ula_prefix() for _ in range(10)}
        assert len(results) > 1, "generate_ula_prefix returned identical values – RNG may be broken"


class TestCreateCa:
    def test_calls_nebula_cert_with_correct_args(self, tmp_path, monkeypatch):
        ca_dir = tmp_path / "ca"
        ca_dir.mkdir()
        fake_bin = "/fake/nebula-cert"

        monkeypatch.setattr("cep.server.network.get_executable_path", lambda _: fake_bin)

        with patch("cep.server.network.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            create_ca("mynet", ca_dir)

        mock_run.assert_called_once_with(
            [
                fake_bin, "ca", "-name", "mynet",
                "-out-crt", ca_dir / "ca.crt",
                "-out-key", ca_dir / "ca.key",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_writes_to_explicit_paths_ignoring_stale_cwd_files(self, tmp_path, monkeypatch):
        """Stale ca.* files in the CWD must neither be moved nor clobber ca_dir."""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "ca.crt").write_text("stale-crt")
        (workdir / "ca.key").write_text("stale-key")
        monkeypatch.chdir(workdir)

        ca_dir = tmp_path / "ca"
        ca_dir.mkdir()

        def _fake_run(cmd, **kwargs):
            # Simulate nebula-cert writing to the explicit -out-* paths
            Path(cmd[cmd.index("-out-crt") + 1]).write_text("fresh-crt")
            Path(cmd[cmd.index("-out-key") + 1]).write_text("fresh-key")
            return MagicMock(returncode=0)

        monkeypatch.setattr("cep.server.network.get_executable_path", lambda _: "/fake/nebula-cert")

        with patch("cep.server.network.subprocess.run", side_effect=_fake_run):
            create_ca("mynet", ca_dir)

        assert (ca_dir / "ca.crt").read_text() == "fresh-crt"
        assert (ca_dir / "ca.key").read_text() == "fresh-key"
        assert (workdir / "ca.crt").read_text() == "stale-crt", "stale ca.crt in cwd must be untouched"
        assert (workdir / "ca.key").read_text() == "stale-key", "stale ca.key in cwd must be untouched"

    def test_raises_500_on_nebula_cert_failure(self, tmp_path, monkeypatch):
        ca_dir = tmp_path / "ca"
        ca_dir.mkdir()
        error = subprocess.CalledProcessError(1, cmd=["nebula-cert"], stderr="boom")

        monkeypatch.setattr("cep.server.network.get_executable_path", lambda _: "/fake/nebula-cert")

        with patch("cep.server.network.subprocess.run", side_effect=error), \
             pytest.raises(HTTPException) as exc_info:
            create_ca("mynet", ca_dir)

        assert exc_info.value.status_code == 500
        assert "boom" in exc_info.value.detail

    def test_returns_ca_dir(self, tmp_path, monkeypatch):
        ca_dir = tmp_path / "ca"
        ca_dir.mkdir()

        monkeypatch.setattr("cep.server.network.get_executable_path", lambda _: "/fake/nebula-cert")

        with patch("cep.server.network.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = create_ca("mynet", ca_dir)

        assert result == ca_dir
