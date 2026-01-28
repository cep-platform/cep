import os
from ipaddress import IPv6Address

import httpx
from fastapi import APIRouter, Response, HTTPException, status

from cloudbox.datamodels import AddAAAARequest

dns_router = APIRouter(prefix="/dns")

hostname = os.environ.get("DNS_IP", "172.17.0.1")
client = httpx.Client(base_url=f"http://{hostname}:8053")


def start_dns(ip: str):
    resp = client.post("/start", json={"subnet": ip})
    resp.raise_for_status()
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
def start(ip: str):

    if not is_valid_ipv6(ip):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid IPv6 address"
        )
    resp = start_dns(ip)
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
