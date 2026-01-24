import platform
import re
import subprocess
from typing import List
from subprocess import run


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

        self.nebula_dns_servers = nebula_dns_ips
        print(self.nebula_dns_servers)
        # self.nebula_dns_servers = ['8.8.8.8', '8.8.4.4']
        self.system_dns_servers = self.get_current_dns_servers()
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
        run(
            ["resolvectl", "dns", self.iface, *self.nebula_dns_ips],
            check=True,
        )
        run(
            ["resolvectl", "domain", self.iface, f'~{self.domain}'],
            check=True,
        )

    def _disable_linux(self):
        pass

    # --------------------
    # macOS (scoped resolver)
    # --------------------

    def _enable_macos(self):
        pass
        # self.set_dns_servers(self.nebula_dns_servers)

    def _disable_macos(self):
        pass
        # self.set_dns_servers(self.system_dns_servers)

    # --------------------
    # Helpers
    # --------------------

    def _extract_dns_servers(self, scutil_output: str) -> List[str]:
        """
        Extract DNS server addresses from `scutil show .../DNS` output.
        Returns a list of IPs (IPv4 or IPv6).
        """
        SERVER_RE = re.compile(r"\b\d+\s*:\s*([0-9a-fA-F:.]+)\b")
        return SERVER_RE.findall(scutil_output)

    def _run_scutil(self, cmds):
        return run(
            ["scutil"],
            input=cmds,
            text=True,
            capture_output=True,
            check=True,
        )

    def _get_primary_service_uuid(self):

        primary_service_uuid_command = """\
open
show State:/Network/Global/IPv4
quit
        """

        res = self._run_scutil(primary_service_uuid_command)
        print(res.stdout)

        # try:
        pattern = r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b"
        match = re.search(pattern, res.stdout)
        if not match:
            raise ValueError("Could not determine primary service, which is needed to set the DNS server")

        primary_service_uuid = match.group(0)
        return primary_service_uuid

    def get_current_dns_servers(self):
        primary_service_uuid = self._get_primary_service_uuid()

        current_dns_command = f"""\
open
show State:/Network/Service/{primary_service_uuid}/DNS
quit
        """

        res = self._run_scutil(current_dns_command)
        return self._extract_dns_servers(res.stdout)

    def set_dns_servers(self, dns_servers: list[str]):
        primary_service_uuid = self._get_primary_service_uuid()
        set_dns_command = f"""
open
d.init
d.add ServerAddresses * {' '.join(dns_servers)}
set State:/Network/Service/{primary_service_uuid}/DNS
quit
        """
        print(set_dns_command)
        self._run_scutil(set_dns_command)
