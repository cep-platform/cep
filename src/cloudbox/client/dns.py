import os
import platform
import subprocess
from pathlib import Path
from typing import List


class NebulaDNS:
    def __init__(
        self,
        nebula_dns_ips: List[str],
        domain: str,
        nebula_iface: str = "nebula1",
    ):
        """
        nebula_dns_ips : list of Nebula DNS IPs (multiple lighthouses)
        nebula_iface   : Nebula interface name (Linux only)
        domain         : routing domain
                         - None  -> sequential for all names
                         - value -> scoped (macOS + Linux)
        """
        if not nebula_dns_ips:
            raise ValueError("nebula_dns_ips must be a non-empty list")

        self.nebula_dns_ips = nebula_dns_ips
        self.iface = nebula_iface
        self.domain = domain
        self.os = platform.system().lower()

    # --------------------
    # Public API
    # --------------------

    def enable(self):
        if self.os == "linux":
            self._enable_linux()
        elif self.os == "darwin":
            self._enable_macos()
        else:
            raise NotImplementedError(f"Unsupported OS: {self.os}")

    def disable(self):
        if self.os == "linux":
            self._disable_linux()
        elif self.os == "darwin":
            self._disable_macos()
        else:
            raise NotImplementedError(f"Unsupported OS: {self.os}")

    # --------------------
    # Linux (systemd-resolved)
    # --------------------

    def _enable_linux(self):
        self._run(
            ["resolvectl", "dns", self.iface, *self.nebula_dns_ips]
        )
        self._run(
            ["resolvectl", "domain", self.iface, f'~{self.domain}']
        )

    def _disable_linux(self):
        pass

    # --------------------
    # macOS (scoped resolver)
    # --------------------

    def _enable_macos(self):
        resolver_dir = Path("/etc/resolver")
        resolver_dir.mkdir(exist_ok=True)

        name = self.domain or "nebula"
        resolver_file = resolver_dir / name

        lines = ["# Nebula DNS (multiple lighthouses)"]
        for ip in self.nebula_dns_ips:
            lines.append(f"nameserver {ip}")

        resolver_file.write_text("\n".join(lines) + "\n")
        os.chmod(resolver_file, 0o644)

    def _disable_macos(self):
        resolver_dir = Path("/etc/resolver")
        name = self.domain or "nebula"
        resolver_file = resolver_dir / name

        if resolver_file.exists():
            resolver_file.unlink()

    # --------------------
    # Helpers
    # --------------------

    def _run(self, cmd):
        subprocess.run(cmd, check=True)

