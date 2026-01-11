import httpx
import json
import os
import typer

from rich import print

from cloudbox.cli.utils import CLOUDBOXCFG_PATH


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

network_app = typer.Typer()


@network_app.command("list")
def _list():
    resp = client.get("/network/list")
    resp.raise_for_status()
    networks = resp.json()
    if networks:
        print('\n'.join(networks))


@network_app.command()
def create(name: str):
    resp = client.get("/network/create", params={'name': name})
    resp.raise_for_status()
