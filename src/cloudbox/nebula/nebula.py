from __future__ import annotations

import ipaddress
import secrets
import shutil
import subprocess
import yaml
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from platformdirs import user_data_dir

from rich import print


APP_NAME = "cloudbox"
DATA_DIR = Path(user_data_dir(APP_NAME))
DATA_DIR.mkdir(exist_ok=True)
LEASEFILE = DATA_DIR / Path('leases.json')


def get_executable_path(name):
    with resources.as_file(resources.files("cloudbox.executables").joinpath(name)) as exe_path:
        path = Path(exe_path)
        path.chmod(0o755)
        return path if path.exists() else None


def get_template_path(name):
    with resources.as_file(
            resources.files("cloudbox.templates").joinpath(name)
            ) as template_path:
        path = Path(template_path)
        return path if path.exists() else None


def generate_ula_prefix():
    # fd + 56 random bits = /64
    random_56bits = secrets.randbits(56)
    prefix = (0xfd << 120) | (random_56bits << 64)
    return ipaddress.IPv6Network((prefix, 64))


@dataclass
class Host():
    name: str
    network: Network
    ip: ipaddress.IPv6Address
    certs: dict[str, Path]
    config_file: Path
    is_lighthouse: bool
    public_ip: str
    
    @property
    def config_files(self):
        config_files = {k: v for k, v in self.certs.items()}
        config_files['config'] = self.config_file
        return config_files


class Network():

    def __init__(self):
        self.network = generate_ula_prefix()
        self.name = self.network.compressed.replace(":", "-").replace("/", "--")

        self.data_dir = DATA_DIR / self.name
        self.data_dir.mkdir(exist_ok=True)

        self.hosts = {}
        self.certs = self.create_ca()

    def random_host_ip(self) -> ipaddress.IPv6Address:
        return ipaddress.IPv6Address(
                int(self.network.network_address) | secrets.randbits(64)
                )

    def create_ca(self):
        nebula_cert_executable_path = get_executable_path('nebula-cert')
        ca_dir = self.data_dir / 'ca'
        ca_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            nebula_cert_executable_path,
            'ca',
            '-name',
            self.name,
            ], capture_output=True, text=True)

        ca_files = list(Path.cwd().glob('ca.*'))
        for file in ca_files:
            file.rename(ca_dir / file.name)

        return ca_files

    def create_host_cert(self, name, ip) -> dict[str, Path]:

        nebula_cert_executable_path = get_executable_path('nebula-cert')
        ca_dir = self.data_dir / 'ca'
        ca_key_path = ca_dir / 'ca.key'
        ca_crt_path = ca_dir / 'ca.crt'

        host_cert_dir = self.data_dir / name
        host_cert_dir.mkdir(exist_ok=True)

        command = [
            nebula_cert_executable_path,
            'sign',
            '-name', name,
            '-ca-crt', ca_crt_path,
            '-ca-key', ca_key_path,
            '-ip', f"{str(ip)}/64",
            ]
        subprocess.run(command, capture_output=True, text=True)

        cert_files_not_yet_in_target_dir = {
                'key': next(Path.cwd().glob(f'{name}.key')),
                'cert': next(Path.cwd().glob(f'{name}.crt')),
                }
        cert_files = {
                key: file.rename(host_cert_dir / file.name)
                for key, file in cert_files_not_yet_in_target_dir.items()
                }
        
        host_ca_crt_path = host_cert_dir / ca_crt_path.name

        shutil.copy(ca_crt_path, host_ca_crt_path)

        cert_files['ca'] = host_ca_crt_path

        return cert_files

    def create_host_config(self, name, cert_files, ip, is_lighthouse) -> Path:
        template_path = get_template_path('config.yml')
        
        with open(template_path) as stream:
            config = yaml.safe_load(stream)

        config['pki'] = {key: str(val) for key, val in cert_files.items()}
        if is_lighthouse:
            config['lighthouse'] = {
                    'am_lighthouse': True
                    }
        else:
            static_host_map = {str(host.ip): [host.public_ip]
                               for host in self.hosts.values()
                               if host.is_lighthouse
                               }
            lighthouse_ips = list(static_host_map.keys())

            config['lighthouse'] = {
                    'am_lighthouse': False,
                    'interval': 60,
                    'hosts': lighthouse_ips,
                    }
            config['static_host_map'] = static_host_map

        config_path = self.data_dir / name / 'config.yml'
        with open(config_path, "w") as f:
            yaml.dump(config, f, sort_keys=False)

        return config_path

    def create_host(self, name, is_lighthouse=True, public_ip=None) -> Host:
        host_ip = self.random_host_ip()
        cert_files = self.create_host_cert(name=name, ip=host_ip)
        config_path = self.create_host_config(name=name,
                                              cert_files=cert_files,
                                              ip=host_ip,
                                              is_lighthouse=is_lighthouse,
                                              )

        host = Host(name=name,
                    network=self,
                    ip=host_ip,
                    certs=cert_files,
                    config_file=config_path,
                    is_lighthouse=is_lighthouse,
                    public_ip=public_ip,
                    )
        self.hosts[name] = host
        return host
