import subprocess
from pathlib import Path
import shutil
import tempfile
import zipfile
import httpx
import yaml
from io import BytesIO
from platformdirs import user_data_dir
import typer

from cloudbox.nebula.nebula import get_executable_path


APP_NAME = "cloudbox_client"
DATA_DIR = Path(user_data_dir(APP_NAME))
DATA_DIR.mkdir(exist_ok=True)
BASE_URL = "http://localhost:8000"
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
    print(resp.json())


@app.command()
def list_hosts(network_name: str, data_dir: Path = DATA_DIR):
    network_dir = data_dir / network_name
    print('\n'.join([
        path.name
        for path in network_dir.glob('*')
        ]))


@app.command()
def create_host(network_name: str,
                host_name: str,
                am_lighthouse: bool = False,
                output_dir: Path = DATA_DIR
                ) -> list[Path]:
    """
    Call /createHost, download the ZIP, and unpack it into output_dir.

    Returns a list of extracted file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    resp = client.get("/createHost", params={'network_name': network_name,
                                             'host_name': host_name,
                                             }
                      )
    resp.raise_for_status()

    if resp.headers.get("content-type") != "application/zip":
        raise ValueError(
            f"Expected ZIP response, got {resp.headers.get('content-type')}"
        )

    extracted_files: list[Path] = []

    tmp_dir = tempfile.TemporaryDirectory()

    with zipfile.ZipFile(BytesIO(resp.content)) as zf:
        for member in zf.namelist():

            temp_path = Path(tmp_dir.name) / member
            with zf.open(member) as src, open(temp_path, "wb") as dst:
                dst.write(src.read())

            extracted_files.append(temp_path)

    config_file = next(filter(lambda x: x.suffix == '.yml',
                              extracted_files
                              )
                       )
    extracted_files = list(filter(lambda x: x.suffix != '.yml',
                                  extracted_files
                                  )
                           )

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    network_name = config['network_name']
    host_name = config['host_name']

    network_dir_path = output_dir / network_name
    network_dir_path.mkdir(exist_ok=True)

    host_dir_path = network_dir_path / host_name
    host_dir_path.mkdir(exist_ok=True)

    target_path_mapping = {
            'key': host_dir_path / f'{host_name}.key',
            'cert': host_dir_path / f'{host_name}.crt',
            'ca': host_dir_path / 'ca.crt',
            }

    config['pki'] = {k: str(v) for k, v in target_path_mapping.items()}
    config_target_path = host_dir_path / 'config.yml'
    with open(config_target_path, 'w') as file:
        yaml.dump(config, file)

    for src in extracted_files:
        dst = target_path_mapping[src.name]
        shutil.copy(src, dst)

    target_path_mapping['config'] = config_target_path
    return target_path_mapping


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


def main():
    app()
