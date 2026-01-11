import httpx
import json
import os
import typer
from pathlib import Path

from rich import print
from platformdirs import user_data_dir


APP_NAME = "cloudbox_cli"
DATA_DIR = Path(user_data_dir(APP_NAME))
DATA_DIR.mkdir(exist_ok=True)
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

network_app = typer.Typer()


@network_app.command("list")
def _list(data_dir: Path = DATA_DIR):
    resp = client.get("/listNetworks")
    resp.raise_for_status()
    networks = resp.json()
    if networks:
        print('\n'.join(networks))


@network_app.command()
def create(name: str):
    resp = client.get("/createNetwork", params={'name': name})
    resp.raise_for_status()
