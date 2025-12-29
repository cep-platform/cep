import httpx
import io
import os
import subprocess
import typer
import yaml
import zipfile
from pathlib import Path
from platformdirs import user_data_dir

from cloudbox.server.datamodels import (
        CertificateRequest,
        HostRequest,
        NetworkRecord,
        )
from cloudbox.utils import get_executable_path, get_template_path


APP_NAME = "cloudbox_client"
DATA_DIR = Path(user_data_dir(APP_NAME))
DATA_DIR.mkdir(exist_ok=True)
BASE_URL = os.environ.get("CLOUDBOX_BASE_URL", "http://localhost:8000")
client = httpx.Client(base_url=BASE_URL)
app = typer.Typer()


@app.command()
def list_networks(data_dir: Path = DATA_DIR):
    resp = client.get("/listNetworks")
    resp.raise_for_status()
    print('\n'.join(resp.json()))


@app.command()
def create_network():
    resp = client.get("/createNetwork")
    resp.raise_for_status()
    resp_data = resp.json()

    network_record = NetworkRecord(
            subnet=resp_data['subnet'],
            hosts=resp_data['hosts']
            )
    print(network_record.name)


@app.command()
def list_hosts(network_name: str, data_dir: Path = DATA_DIR):
    network_dir = data_dir / network_name
    print('\n'.join([
        path.name
        for path in network_dir.glob('*')
        ]))


def get_host_ip(network_name: str):
    resp = client.get("/getHostIp", params=network_name)
    return resp.json()


@app.command()
def create_host(network_name: str,
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
        config['lighthouse'] = {'am_lighthouse': True}
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


@app.command()
def connect(network_name: str, host_name: str, data_dir: Path = DATA_DIR):
    nebula_executable_path = get_executable_path('nebula')
    config_path = data_dir / network_name / host_name / 'config.yml'
    command = [
        nebula_executable_path,
        '-config', str(config_path)
        ]
    print(f"Connecting to {network_name} as {host_name}")
    subprocess.run(command, check=True)


if __name__ == "__main__":
    app()
