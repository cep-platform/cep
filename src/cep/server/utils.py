"""Server-local path configuration.

Persistence lives in `cep.server.db`, which resolves its locations from
`SERVER_DATA_DIR` lazily so tests can redirect them via monkeypatch.
"""
from __future__ import annotations

from pathlib import Path

from cep.utils import DATA_DIR

SERVER_DATA_DIR = DATA_DIR / 'server'
SERVER_DATA_DIR.mkdir(exist_ok=True)
CEP_SERVER_CFG_PATH = Path.home() / '.cepservercfg'


def load_AAAA_records() -> dict[str, str]:
    pass


def write_AAAA_records(domain_names: dict[str, str]) -> None:
    pass
