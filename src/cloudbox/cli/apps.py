import typer
from rich import print

from cloudbox.cli.utils import get_client, CLI_DATA_DIR


apps_app = typer.Typer()
client = get_client("/apps")


@apps_app.command("list")
def _list():
    raise NotImplementedError()
    resp = client.get("/list")
    resp.raise_for_status()
    apps = resp.json()
    if apps:
        print('\n'.join(apps))


@apps_app.command()
def create(name: str):
    raise NotImplementedError()
    resp = client.get("/create", params={'name': name})
    resp.raise_for_status()


@apps_app.command()
def show(name: str):
    raise NotImplementedError()
    resp = client.get("/show", params={'name': name})
    resp.raise_for_status()
    print(resp.json())


@apps_app.command()
def delete(name: str):
    raise NotImplementedError()
    resp = client.delete("/delete", params={'name': name})
    resp.raise_for_status()


@apps_app.command()
def edit(name: str):
    raise NotImplementedError()


@apps_app.command()
def deploy(name: str):
    raise NotImplementedError()
