import httpx
import json
import os
import typer
from pathlib import Path

from cloudbox.cli.network import network_app
from cloudbox.cli.host import host_app
from cloudbox.cli.server import server_app


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

app = typer.Typer()
app.add_typer(network_app, name="network")
app.add_typer(host_app, name="host")
app.add_typer(server_app, name="server")


@app.command()
def auth():
    cloudbox_server_url = input("cloudbox server instance url: ")
    token = input("token: ")
    with open('.cloudboxcfg', 'w') as f:
        json.dump({
            'base_url': cloudbox_server_url,
            'token': token,
            }, f)
