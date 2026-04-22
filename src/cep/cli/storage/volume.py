import typer
from rich import print

from cep.storage.docker import Volume, list_all_volumes
from cep.cli.utils import get_client, CLI_DATA_DIR

volume_app = typer.Typer()

client = get_client("/storage/volumes")


@volume_app.command('create')
def create(pool_name: str, name: str):
    resp = client.get("/create", params={'pool_name': pool_name, 'name': name})
    resp.raise_for_status()


@volume_app.command('delete')
def delete(pool_name: str, name: str):
    resp = client.delete("/delete", params={'name': name})
    resp.raise_for_status()


@volume_app.command('list')
def _list(pool_name: str | None = None):
    resp = client.get("/list")
    resp.raise_for_status()
    volumes = resp.json()
    if volumes:
        print('\n'.join(volumes))


@volume_app.command('show')
def show(pool_name: str, name: str):
    resp = client.get("/show", params={'name': name})
    resp.raise_for_status()
    print(resp.json())
