import os
from ipaddress import IPv6Address

import httpx
from fastapi import APIRouter, Response, HTTPException, Body

from cep.datamodels import AddAAAARequest
from cep.server.utils import load_db

dns_router = APIRouter(prefix="/dns")

hostname = os.environ.get("DNS_IP", "localhost")
dns_token = os.environ.get("DNS_TOKEN", None)
base_url = f"http://{hostname}:8053"
if dns_token:
    client = httpx.Client(
                    base_url=base_url,
                    headers={
                        "Authorization": f"Bearer {dns_token}",
                        },
                    )
else:
    client = httpx.Client(base_url=base_url)


def start_dns(subnet: str):
    resp = client.post("/start", json={"subnet": subnet})
    return resp


def stop_dns():
    resp = client.post("/stop")
    return resp


def add_host_to_dns(aaaa_request: AddAAAARequest):
    resp = client.post("/records", json=aaaa_request.model_dump(mode="json"))
    return resp


def remove_host_from_dns(name: str):
    resp = client.delete(f"/records/{name}")
    return resp


def is_valid_ipv6(address: str) -> bool:
    try:
        IPv6Address(address)
        return True
    except ValueError:
        return False


@dns_router.post("/start")
def start(network_name: str = Body(..., embed=True)):
    network_store = load_db()

    network_record = network_store.networks.get(network_name, None)
    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{network_name}' not found",
                )

    # Get first ip in range for DNS
    subnet = str(network_record.subnet)
    resp = start_dns(subnet)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )


@dns_router.get("/stop")
def stop():
    resp = stop_dns()
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )


@dns_router.post("/records")
def add(aaaa_request: AddAAAARequest):
    resp = add_host_to_dns(aaaa_request)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )


@dns_router.delete("/remove/{name}")
def remove(name: str):
    resp = remove_host_from_dns(name)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )
