from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from io import BytesIO
from ipaddress import IPv6Address, IPv6Network
from pathlib import Path
from platformdirs import user_data_dir
import json
import secrets
import subprocess
import tempfile
import zipfile

from cloudbox.utils import get_executable_path
from cloudbox.server.datamodels import (
        NetworkRecord,
        NetworkStore,
        HostRecord,
        CertificateRequest,
        HostRequest,
        )

APP_NAME = "cloudbox"
DATA_DIR = Path(user_data_dir(APP_NAME))
DATA_DIR.mkdir(exist_ok=True)
CA_DIR = DATA_DIR / 'ca'
CA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'db.json'

app = FastAPI()


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


def generate_ula_prefix():
    random_56bits = secrets.randbits(56)
    prefix = (0xfd << 120) | (random_56bits << 64)
    return IPv6Network((prefix, 64))


def random_host_ip(prefix) -> IPv6Address:
    return IPv6Address(
            int(prefix.network_address) | secrets.randbits(64)
            )


def create_ca(name: str = 'my_ca', ca_dir: Path = CA_DIR):
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


ca_dir = create_ca()


@app.get("/listNetworks")
def list_networks() -> list[str]:
    return [path.name for path in DATA_DIR.glob('*-*-*-*--x64')]


@app.get("/createNetwork")
def create_network() -> NetworkRecord:
    subnet = generate_ula_prefix()
    network_record = NetworkRecord(subnet=subnet, hosts={})

    network_data_dir = DATA_DIR / network_record.name
    network_data_dir.mkdir(exist_ok=True)

    network_store = load_db()
    network_store.networks[network_record.name] = network_record
    save_db(network_store)

    return network_record


@app.get("/getNetwork")
def get_network(name: str) -> NetworkRecord:
    network_store = load_db()
    return network_store.networks.get(name, None)


@app.get("/getLighthouseMapping")
def get_lighthouse_mapping(network_name: str) -> dict:
    network_store = load_db()
    network_record = network_store.networks.get(network_name, None)

    lighthouse_mapping = {
            str(host.ip): f"[{str(host.public_ip)}]:4242"
            for host in network_record.hosts.values()
            if host.is_lighthouse
            }
    return lighthouse_mapping


@app.post("/createHost")
def create_host(request: HostRequest) -> HostRecord:
    network_store = load_db()
    network_record = network_store.networks.get(request.network_name, None)

    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{request.network_name}' not found",
            )

    if network_record.hosts.get(request.name, False):
        raise HTTPException(
                status_code=409,
                detail=f"Host '{request.name}' already exists in network '{request.network_name}'",
            )

    host_record = HostRecord(
            name=request.name,
            ip=random_host_ip(network_record.subnet),
            groups=[],
            is_lighthouse=request.is_lighthouse,
            public_ip=request.public_ip,
            )

    network_record.hosts[request.name] = host_record
    save_db(network_store)

    return host_record


@app.post("/signCert")
def sign_cert(request: CertificateRequest):
    network_name = request.network_name
    host_name = request.host_name

    network_store = load_db()
    network_record = network_store.networks.get(network_name)
    host_record = network_record.hosts.get(host_name)
    ip = f"{host_record.ip}/64"

    tempdir = Path(tempfile.TemporaryDirectory(delete=False).name)

    cert_path = tempdir / f"{host_name}.crt"
    pub_key_path = tempdir / f"{host_name}.pub"
    with open(pub_key_path, 'w') as f:
        f.write(request.pub_key)

    ca_cert_path = CA_DIR / 'ca.crt'
    nebula_cert_executable_path = get_executable_path('nebula-cert')
    subprocess.run([
        nebula_cert_executable_path,
        'sign',
        '-in-pub', pub_key_path,
        '-name', host_name,
        '-ip', ip,
        '-ca-crt', ca_cert_path,
        '-ca-key', CA_DIR / 'ca.key',
        '-out-crt', cert_path,
        ], capture_output=True, text=True)

    zip_path = Path(tempdir) / "nebula-certs.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(cert_path, arcname=cert_path.name)
        z.write(ca_cert_path, arcname=ca_cert_path.name)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="nebula-certs.zip",
    )
