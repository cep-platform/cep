import json
from pathlib import Path

from cep.datamodels import NetworkStore
from cep.utils import DATA_DIR


SERVER_DATA_DIR = DATA_DIR / 'server'
SERVER_DATA_DIR.mkdir(exist_ok=True)
DB_PATH = SERVER_DATA_DIR / 'db.json'
CEP_SERVER_CFG_PATH = Path.home() / '.cepservercfg'

def load_db() -> NetworkStore:
    if not DB_PATH.exists():
        return NetworkStore(networks={})

    with DB_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    return NetworkStore.model_validate(raw)


def save_db(store: NetworkStore) -> None:
    with DB_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            store.model_dump(),
            f,
            indent=2,
            sort_keys=True,
        )


def load_AAAA_records() -> dict[str, str]:
    pass


def write_AAAA_records(domain_names: dict[str, str]) -> None:
    pass
