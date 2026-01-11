import httpx
import io
import json
import os
import subprocess
import time
import typer
import zipfile
from pathlib import Path

import psutil
import yaml
from rich import print
from platformdirs import user_data_dir

from cloudbox.cli.dns import NebulaDNS
from cloudbox.server.datamodels import (
        CertificateRequest,
        HostRequest,
        )
from cloudbox.utils import get_executable_path, get_template_path


APP_NAME = "cloudbox_cli"
DATA_DIR = Path(user_data_dir(APP_NAME))
DATA_DIR.mkdir(exist_ok=True)
CLOUDBOXCFG_PATH = Path('.cloudboxcfg')

if CLOUDBOXCFG_PATH.exists():
    with open(CLOUDBOXCFG_PATH, 'r') as f:
        cloudbox_cfg = json.load(f)
else:
    cloudbox_cfg = {}

BASE_URL = (
        os.environ.get("CLOUDBOX_BASE_URL")
        or
        cloudbox_cfg.get('base_url', "http://localhost:8000")
        )
TOKEN = os.environ.get("CLOUDBOX_TOKEN") or cloudbox_cfg.get('token', None)

if TOKEN:
    client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                },
            )
else:
    client = httpx.Client(base_url=BASE_URL)
host_app = typer.Typer()


@host_app.command("list")
def _list(network_name: str, data_dir: Path = DATA_DIR):
    network_dir = data_dir / network_name
    print('\n'.join([
        path.name
        for path in network_dir.glob('*')
        ]))


def get_host_ip(network_name: str):
    resp = client.get("/getHostIp", params=network_name)
    return resp.json()


@host_app.command()
def create(network_name: str,
           host_name: str,
           am_lighthouse: bool = False,
           public_ip: str = None,
           output_dir: Path = DATA_DIR
           ) -> list[Path]:

    if am_lighthouse and not public_ip:
        raise ValueError("public_ip should be set when am lighthouse is set to True")

    nebula_cert_executable_path = get_executable_path('nebula-cert')

    network_path = DATA_DIR / network_name
    network_path.mkdir(exist_ok=True)

    host_data_path = network_path / host_name
    host_data_path.mkdir(exist_ok=True)

    priv_key_path = host_data_path / f'{host_name}.key'
    pub_key_path = host_data_path / f'{host_name}.pub'
    crt_path = host_data_path / f'{host_name}.crt'
    ca_crt_path = host_data_path / 'ca.crt'
    config_out_path = host_data_path / 'config.yml'

    subprocess.run([
        nebula_cert_executable_path,
        'keygen',
        '-out-key', priv_key_path,
        '-out-pub', pub_key_path,
        ], capture_output=True, text=True)

    with open(pub_key_path, 'r') as f:
        pub_key = f.read()

    host_request = HostRequest(
            name=host_name,
            network_name=network_name,
            is_lighthouse=am_lighthouse,
            public_ip=public_ip,
            )
    host_response = client.post(
            "/createHost",
            json=host_request.model_dump(mode="json")
            )
    host_response.raise_for_status()
    ip = host_response.json()['ip']

    certificate_request = CertificateRequest(
            network_name=network_name,
            host_name=host_name,
            pub_key=pub_key,
            )

    cert_response = client.post(
            "/signCert",
            json=certificate_request.model_dump(mode='json')
            )
    cert_response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(cert_response.content)) as z:
        z.extractall(host_data_path)

    config_path = get_template_path('config.yml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    pki = {
            'key': str(priv_key_path),
            'cert': str(crt_path),
            'ca': str(ca_crt_path),
            }

    config['pki'] = pki

    if am_lighthouse:
        config['lighthouse'] = {'am_lighthouse': True,
                                'serve_dns': True,
                                'dns': {
                                    'host': f'{ip}',
                                    'port': 53,
                                    }
                                }
        config['firewall']['inbound'].append({
            'port': 53,
            'proto': 'udp',
            'host': 'any',
            })
    else:
        lighthouse_mapping_response = client.get(
                "/getLighthouseMapping",
                params={'network_name': network_name}
                )
        lighthouse_mapping_response.raise_for_status()
        static_host_map = lighthouse_mapping_response.json()
        config['static_host_map'] = static_host_map
        config['lighthouse'] = {'am_lighthouse': False,
                                'interval': 60,
                                'hosts': list(static_host_map.keys())}

    with open(config_out_path, 'w') as f:
        yaml.safe_dump(config, f)


def ip_exists(ip):
    for if_addrs in psutil.net_if_addrs().values():
        for addr in if_addrs:
            if addr.address == ip:
                return True
    return False


def wait_for_interface(ip_address: str, timeout: float = 10.0):
    start = time.time()
    while time.time() - start < timeout:
        if ip_exists(ip=ip_address):
            return True
    return False


@host_app.command()
def connect(network_name: str, host_name: str, data_dir: Path = DATA_DIR):
    nebula_executable_path = get_executable_path("nebula")
    nebula_cert_executable_path = get_executable_path("nebula-cert")
    config_path = data_dir / network_name / host_name / "config.yml"

    with open(config_path) as f:
        config = yaml.safe_load(f)

    am_lighthouse = config["lighthouse"]["am_lighthouse"]
    cert_path = config['pki']['cert']

    result = subprocess.run([
        nebula_cert_executable_path,
        'print',
        '-path', cert_path,
        ], capture_output=True, text=True)
    tld = json.loads(result.stdout)['details']['name'].split('.')[-1]
    ip = json.loads(result.stdout)['details']['networks'][0].split('/')[0]

    command = [
            nebula_executable_path,
            "-config", str(config_path),
            ]

    print(f"Connecting to {network_name} as {host_name}")

    proc = subprocess.Popen(command)

    dns = None
    try:
        if not am_lighthouse:
            if not wait_for_interface(ip):
                raise RuntimeError("nebula interface did not appear")

            lighthouses = config["lighthouse"]["hosts"]

            dns = NebulaDNS(
                    nebula_iface="nebula1",
                    nebula_dns_ips=lighthouses,
                    domain=tld,
                    )
            dns.enable()

        # Wait for nebula to exit
        proc.wait()

    finally:
        if dns:
            dns.disable()

        if proc.poll() is None:
            proc.terminate()
            proc.wait()
