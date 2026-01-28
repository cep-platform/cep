import io
import json
import os
import shutil
import signal
import subprocess
import time
import typer
import zipfile
from pathlib import Path

import psutil
import yaml
from rich import print

from cloudbox.cli.dns import NebulaDNS
from cloudbox.datamodels import (
        CertificateRequest,
        HostRequest,
        )
from cloudbox.utils import (
        get_executable_path,
        get_template_path,
        )
from cloudbox.cli.utils import (
        CLI_DATA_DIR,
        get_client,
        )

RUNTIME_PATH = CLI_DATA_DIR / "runtime.json"

client = get_client("/host")
host_app = typer.Typer()


@host_app.command("list")
def _list(network_name: str, data_dir: Path = CLI_DATA_DIR):
    network_dir = data_dir / network_name
    print('\n'.join([
        path.name
        for path in network_dir.glob('*')
        ]))


@host_app.command()
def create(network_name: str,
           host_name: str,
           am_lighthouse: bool = False,
           public_ip: str = None,
           output_dir: Path = CLI_DATA_DIR
           ) -> list[Path]:

    if am_lighthouse and not public_ip:
        raise ValueError("public_ip should be set when am lighthouse is set to True")

    if not am_lighthouse:
        network_client = get_client("/network")
        lighthouse_mapping_response = network_client.get(
                "/lighthouses",
                params={'network_name': network_name}
                )
        lighthouse_mapping_response.raise_for_status()
        static_host_map = lighthouse_mapping_response.json()
        if not static_host_map:
            raise ValueError('First host in the network should be created as a lighthouse. Please use --am-lighthouse and --public-ip to create a lighthouse')

    nebula_cert_executable_path = get_executable_path('nebula-cert')

    network_path = CLI_DATA_DIR / network_name
    host_data_path = network_path / host_name
    host_data_path.mkdir(exist_ok=True, parents=True)

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
            "/create",
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
            "/sign",
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
        config['lighthouse'] = {'am_lighthouse': True}
        config['firewall']['inbound'].append({
            'port': 53,
            'proto': 'udp',
            'host': 'any',
            })
    else:
        config['static_host_map'] = static_host_map
        config['lighthouse'] = {'am_lighthouse': False,
                                'interval': 60,
                                'hosts': list(static_host_map.keys())
                                }

    with open(config_out_path, 'w') as f:
        yaml.safe_dump(config, f)


@host_app.command()
def delete(network_name: str,
           host_name: str,
           output_dir: Path = CLI_DATA_DIR
           ) -> list[Path]:

    host_response = client.delete(
            "/delete",
            params={'network_name': network_name,
                    'host_name': host_name,
                    },
            )
    host_response.raise_for_status()

    host_path = CLI_DATA_DIR / network_name / host_name
    shutil.rmtree(host_path)


@host_app.command()
def show(network_name: str,
         host_name: str,
         output_dir: Path = CLI_DATA_DIR
         ) -> list[Path]:

    host_response = client.get(
            "/show",
            params={'network_name': network_name,
                    'host_name': host_name,
                    },
            )
    host_response.raise_for_status()
    host_config_path = CLI_DATA_DIR / network_name / host_name / 'config.yml'
    with open(host_config_path, 'r') as f:
        config = yaml.safe_load(f)

    host_data = {'server': host_response.json(), 'client': config}
    print(host_data)


@host_app.command()
def edit(network_name: str,
         host_name: str,
         output_dir: Path = CLI_DATA_DIR
         ) -> list[Path]:

    host_config_path = CLI_DATA_DIR / network_name / host_name / 'config.yml'
    if not host_config_path.exists():
        raise ValueError(f"Host config path {str(host_config_path)} does not exist")
    typer.edit(filename=str(host_config_path))


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
def connect(network_name: str,
            host_name: str,
            data_dir: Path = CLI_DATA_DIR,
            detach: bool = False,
            ):
    nebula_executable_path = get_executable_path("nebula")
    nebula_cert_executable_path = get_executable_path("nebula-cert")
    config_path = data_dir / network_name / host_name / "config.yml"
    if_name = "nebula1"

    if detach:
        runtime = {}

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

    proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            # stdout=subprocess.DEVNULL,
            # stderr=subprocess.DEVNULL,
            start_new_session=True,
            )
    if detach:
        runtime['pid'] = proc.pid

    dns = None
    try:
        if not am_lighthouse:
            if not wait_for_interface(ip):
                raise RuntimeError("nebula interface did not appear")

            lighthouses = config["lighthouse"]["hosts"]

            dns = NebulaDNS(
                    nebula_iface=if_name,
                    nebula_dns_ips=lighthouses,
                    domain=tld,
                    )
            if detach:
                runtime['if_name'] = if_name
                runtime['lighthouses'] = lighthouses
                runtime['tld'] = tld
            dns.enable()

        if not detach:
            # Wait for nebula to exit
            proc.wait()
        else:
            RUNTIME_PATH.write_text(json.dumps(runtime))

    finally:
        if not detach:
            if dns:
                dns.disable()

            if proc.poll() is None:
                proc.terminate()
                proc.wait()


@host_app.command()
def disconnect(data_dir: Path = CLI_DATA_DIR):
    runtime = json.loads(RUNTIME_PATH.read_text())
    NebulaDNS(nebula_iface=runtime["if_name"],
              nebula_dns_ips=runtime["lighthouses"],
              domain=runtime["tld"],
              ).disable()
    os.kill(runtime['pid'], signal.SIGTERM)
