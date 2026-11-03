from __future__ import annotations

from dotenv import load_dotenv
from typing import Optional
import copy
import httpx
import os

from uvicorn.config import LOG_LEVELS as UVICORN_LOG_LEVELS
from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING_CONFIG

from cep.utils import DATA_DIR

load_dotenv()

CLI_DATA_DIR = DATA_DIR / 'cli'
CLI_DATA_DIR.mkdir(exist_ok=True)


def get_client(path: str = None) -> httpx.Client:

    BASE_URL = os.environ.get("CEP_SERVER_URL", "http://localhost:8000")

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


def uvicorn_log_config(level: str) -> dict:
    """
    Uvicorn's default logging config, retargeted at `level`.

    The stock config only covers the `uvicorn.*` loggers and leaves the
    root logger alone, so application-level logging (e.g. the debug lines
    in cep.server.apps) would never be emitted. This wires the root logger
    through uvicorn's default handler at the same level. The uvicorn reload
    subprocess re-runs configure_logging() on worker startup, so
    live-reload workers emit app logs at `level` too.

    Pass the result to `uvicorn.run(log_level=level, log_config=...)`.
    Raises ValueError for an unknown level.
    """
    level = level.lower()
    if level not in UVICORN_LOG_LEVELS:
        raise ValueError(
            f"unknown log level '{level}', expected one of: "
            + ", ".join(sorted(UVICORN_LOG_LEVELS))
        )
    config = copy.deepcopy(UVICORN_LOGGING_CONFIG)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        config["loggers"][logger_name]["level"] = level.upper()
    config["root"] = {"handlers": ["default"], "level": level.upper()}
    return config
