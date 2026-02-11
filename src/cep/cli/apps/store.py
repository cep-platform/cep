from typing import Optional
import typer
from rich import print
import uvicorn

from cep.cli.utils import get_client, parse_available

store_app = typer.Typer()
client_proxy = get_client("/apps/store")


@store_app.command("list")
def _list():
    resp = client_proxy.get("/listProxy")
    resp.raise_for_status()
    apps = resp.json()
    if apps:
        print('\n'.join(apps))
