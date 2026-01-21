from typing import Optional
import httpx
import json
import os
from pathlib import Path

from cloudbox.utils import DATA_DIR

CLI_DATA_DIR = DATA_DIR / 'cli'
CLI_DATA_DIR.mkdir(exist_ok=True)
CLOUDBOXCFG_PATH = Path.home() / '.cloudboxcfg'


def get_client(path: str = None) -> httpx.Client:
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
    if path:
        BASE_URL = BASE_URL + path

    TOKEN = os.environ.get("CLOUDBOX_TOKEN") or cloudbox_cfg.get('token', None)

    if TOKEN:
        return httpx.Client(
                base_url=BASE_URL,
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    },
                )
    else:
        return httpx.Client(base_url=BASE_URL)

def parse_available(apps: list[dict], verbose: Optional[bool]):
    n_apps = len(apps)
    print("Found {0} apps running".format(n_apps))
    for idx, app in enumerate(apps):
        if verbose:
            print("\n")
            print(app)
            print("\n--------------------------------")
        else:
            print(
                "Image no.{0} : Runnig image {1}, created at {2} and running for {3} with size: {4}".format(idx + 1, 
                    app.get("Image"),
                    app.get("CreatedAt"),
                    app.get("RunningFor"),
                    app.get("Size")
                )
            )

def get_apps_client(path: str) -> httpx.Client:
    #TODO: Add cloudbox CFG auth
    BASE_URL = "http://localhost:8080" + path
    return httpx.Client(base_url=BASE_URL)
