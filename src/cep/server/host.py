import secrets
import subprocess
import tempfile
import zipfile
from ipaddress import IPv6Address
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.exceptions import HTTPException

from cep.utils import get_executable_path
from cep.datamodels import (
        HostRecord,
        CertificateRequest,
        HostRequest,
        AddAAAARequest
        )
from cep.server.utils import (
        SERVER_DATA_DIR,
        save_db,
        load_db,
        )
from cep.server.dns import (
        add_host_to_dns,
        remove_host_from_dns,
        )

host_router = APIRouter(prefix="/host")


def random_host_ip(prefix) -> IPv6Address:
    return IPv6Address(
            int(prefix.network_address) | secrets.randbits(64)
            )


@host_router.post("/create")
def create(request: HostRequest) -> HostRecord:
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

    if len(network_record.hosts) == 0:
        # First host gets [subnet]::1, the rest gets random ips
        ip = next(network_record.subnet.hosts())
    else:
        ip = random_host_ip(network_record.subnet)

    host_record = HostRecord(
            name=request.name,
            ip=ip,
            groups=[],
            is_lighthouse=request.is_lighthouse,
            public_ip=request.public_ip,
            )

    if request.add_dns_record:
        domain_name = f"{request.name}.{network_record.name}"
        aaaa_request = AddAAAARequest(name=domain_name, ip=str(ip))
        add_host_to_dns(aaaa_request)

    network_record.hosts[request.name] = host_record
    save_db(network_store)

    return host_record


@host_router.delete("/delete")
def delete(network_name: str, host_name: str):
    network_store = load_db()
    network_record = network_store.networks.get(network_name, None)
    try:
        del network_record.hosts[host_name]
        save_db(network_store)
        remove_host_from_dns(name=host_name)
    except KeyError:
        raise HTTPException(
                status_code=404,
                detail=f"Host {host_name} not found in {network_name}",
                )
    return {"status": "deleted"}


@host_router.get("/show")
def show(network_name: str, host_name: str) -> HostRecord:
    network_store = load_db()
    network_record = network_store.networks.get(network_name, None)
    if network_record is None:
        raise HTTPException(
                status_code=404,
                detail=f"Network {network_name} not found",
                )

    host_record = network_record.hosts.get(host_name, None)
    if host_record is None:
        raise HTTPException(
                status_code=404,
                detail=f"Host {host_name} not found in {network_name}",
                )
    return host_record


@host_router.post("/sign")
def sign(request: CertificateRequest):
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

    ca_cert_path = SERVER_DATA_DIR / network_name / 'ca.crt'
    ca_key_path = SERVER_DATA_DIR / network_name / 'ca.key'
    nebula_cert_executable_path = get_executable_path('nebula-cert')
    subprocess.run([
        nebula_cert_executable_path,
        'sign',
        '-in-pub', pub_key_path,
        '-name', f'{host_name}.{network_name}',
        '-ip', ip,
        '-ca-crt', ca_cert_path,
        '-ca-key', ca_key_path,
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
