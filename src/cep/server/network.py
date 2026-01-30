import secrets
import shutil
import subprocess
from ipaddress import IPv6Address, IPv6Network
from pathlib import Path

from fastapi import APIRouter, HTTPException

from cep.utils import get_executable_path
from cep.datamodels import NetworkRecord
from cep.server.utils import (
        SERVER_DATA_DIR,
        save_db,
        load_db,
        )

from cep.server.dns import (
        start_dns,
        stop_dns,
        )


network_router = APIRouter(prefix="/network")


def generate_ula_prefix() -> IPv6Network:
    random_56bits = secrets.randbits(56)
    prefix = (0xfd << 120) | (random_56bits << 64)
    return IPv6Network((prefix, 64))


def create_ca(name: str, ca_dir: Path) -> Path:
    nebula_cert_executable_path = get_executable_path('nebula-cert')
    subprocess.run([
        nebula_cert_executable_path,
        'ca',
        '-name',
        name,
        ], capture_output=True, text=True)

    ca_files = list(Path.cwd().glob('ca.*'))
    for file in ca_files:
        file.rename(ca_dir / file.name)

    return ca_dir


@network_router.get("/list")
def _list() -> list[str]:
    return [path.name for path in SERVER_DATA_DIR.glob('*') if path.name != 'db.json']


@network_router.get("/create")
def create(name: str, dns: bool) -> NetworkRecord:
    subnet = generate_ula_prefix()
    network_record = NetworkRecord(name=name, subnet=subnet, hosts={}, dns=dns)

    network_data_dir = SERVER_DATA_DIR / network_record.name
    network_data_dir.mkdir(exist_ok=True)

    create_ca(name=name, ca_dir=network_data_dir)

    network_store = load_db()
    network_store.networks[network_record.name] = network_record
    save_db(network_store)

    if dns:
        start_dns(subnet=str(subnet))

    return network_record


@network_router.delete("/delete")
def delete(name: str):
    network_data_dir = SERVER_DATA_DIR / name
    if not network_data_dir.exists():
        raise HTTPException(status_code=404, detail="Network data not found")

    # Delete directory and contents
    shutil.rmtree(network_data_dir)

    # Delete from DB
    network_store = load_db()
    if name not in network_store.networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    if network_store.networks[name].dns:
        stop_dns()

    del network_store.networks[name]
    save_db(network_store)

    

    # Return nothing (204 No Content)
    return


@network_router.get("/show")
def show(name: str) -> NetworkRecord:
    network_store = load_db()
    response = network_store.networks.get(name, None)
    if response:
        return response
    else:
        raise HTTPException(status_code=404, detail="Network not found")


@network_router.get("/lighthouses")
def lighthouses(network_name: str) -> dict:
    network_store = load_db()
    network_record = network_store.networks.get(network_name, None)
    if not network_record:
        raise HTTPException(status_code=404, detail="Network not found")

    lighthouse_mapping = {
            str(host.ip): f"[{str(host.public_ip)}]:4242" if isinstance(host.public_ip, IPv6Address) else f"{str(host.public_ip)}:4242"
            for host in network_record.hosts.values()
            if host.is_lighthouse
            }
    return lighthouse_mapping
