import typer

from rich import print

from cloudbox.cli.utils import get_client


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
def create(name: str):
    resp = client.get("/create", params={'name': name})
    resp.raise_for_status()
