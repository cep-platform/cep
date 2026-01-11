import httpx
import json
import os
from pathlib import Path

from cloudbox.utils import DATA_DIR

CLI_DATA_DIR = DATA_DIR / 'cli'
CLI_DATA_DIR.mkdir(exist_ok=True)
CLOUDBOXCFG_PATH = Path.home() / '.cloudboxcfg'


def get_client(path: str = None):
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
