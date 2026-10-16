import shutil

import typer
from rich import print

from cep.cli.utils import get_client, CLI_DATA_DIR
from cep.datamodels import NetworkCreateRequest


network_app = typer.Typer()
client = get_client("/network")


@network_app.command("list")
def _list():
    resp = client.get("/list")
    resp.raise_for_status()
    networks = resp.json()
    if networks:
        print('\n'.join(networks))


@network_app.command()
def create(name: str, dns: bool = True):
    request = NetworkCreateRequest(name=name, dns=dns)
    resp = client.post("/create", json=request.model_dump(mode="json"))
    if resp.status_code == 409:
        print(f"[red]Error:[/red] {resp.json()['detail']}")
        raise typer.Exit(1)
    resp.raise_for_status()


@network_app.command()
def show(name: str):
    resp = client.get("/show", params={'name': name})
    resp.raise_for_status()
    print(resp.json())


@network_app.command()
def delete(name: str):
    resp = client.delete("/delete", params={'name': name})
    resp.raise_for_status()
    network_data_dir = CLI_DATA_DIR / name
    shutil.rmtree(network_data_dir, ignore_errors=True)


@network_app.command()
def lighthouses(name: str):
    resp = client.get("/lighthouses", params={'network_name': name})
    resp.raise_for_status()
    print(resp.json())
