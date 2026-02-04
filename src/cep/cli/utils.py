from dotenv import load_dotenv
from typing import Optional
import httpx
import os

from cep.utils import DATA_DIR

load_dotenv()

CLI_DATA_DIR = DATA_DIR / 'cli'
CLI_DATA_DIR.mkdir(exist_ok=True)


def get_client(path: str = None) -> httpx.Client:

    BASE_URL = os.environ.get("CEP_BASE_URL", "http://localhost:8000")

    if path:
        BASE_URL = BASE_URL + path

    TOKEN = os.environ.get("CEP_SERVER_TOKEN", None)

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
    #TODO: Add cep CFG auth
    BASE_URL = "http://localhost:8080" + path
    return httpx.Client(base_url=BASE_URL)
