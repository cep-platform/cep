import os

from typing import Optional
from fastapi import APIRouter, Response
import httpx
from fastapi.exceptions import HTTPException
import requests

from cep.apps.caddy import CaddyReverseProxy
from cep.apps.docker import PROXY_PORT_LABEL
from cep.datamodels import AppRecord, AddAAAARequest
from cep.server.apps.store import store_router
from cep.server.dns import add_host_to_dns, remove_host_from_dns
from cep.server.utils import load_db, save_db

apps_router = APIRouter(prefix="/apps")
apps_router.include_router(store_router)

hostname = os.environ.get("APP_STORE_HOST_NAME", "localhost")
client = httpx.Client(base_url=f"http://{hostname}:8080")


def _appstore_error(resp: httpx.Response, fallback: str) -> HTTPException:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = None
    return HTTPException(
            status_code=resp.status_code,
            detail=str(detail) if detail else fallback,
            )


def _deployed_service(resp: httpx.Response, name: str) -> dict:
    services = resp.json().get("services", {})
    if len(services) != 1:
        raise HTTPException(
                status_code=500,
                detail=(
                    f"App template '{name}' must define exactly one service, "
                    f"got {len(services)}"
                    ),
                )
    return next(iter(services.values()))


@apps_router.post("/deployProxy")
def deploy(name: str, network_name: str):
    network_store = load_db()
    network_record = network_store.networks.get(network_name)

    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{network_name}' not found",
                )

    if name in network_record.apps:
        raise HTTPException(
                status_code=409,
                detail=f"App '{name}' is already deployed in network '{network_name}'",
                )

    cep = network_record.get_cep()
    if cep is None:
        raise HTTPException(
                status_code=409,
                detail=(
                    f"Network '{network_name}' has no cep host; create the "
                    "network's first host before deploying apps"
                    ),
                )
    host_name = f"{name}.{cep.name}.{network_name}"

    try:
        resp = client.post("/deploy", params={"name": name})
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"Appstore unreachable while deploying '{name}': {e}",
                )
    if resp.is_error:
        raise _appstore_error(resp, f"Appstore deploy of '{name}' failed")

    service = _deployed_service(resp, name)
    container_name = service.get("container_name")
    rproxy_port = (service.get("labels") or {}).get(PROXY_PORT_LABEL)
    if not container_name or not rproxy_port:
        raise HTTPException(
                status_code=500,
                detail=(
                    f"App template '{name}' must define 'container_name' and "
                    f"the '{PROXY_PORT_LABEL}' label"
                    ),
                )

    try:
        CaddyReverseProxy.add_rproxy(
                hostname=host_name,
                destination=f"{container_name}:{rproxy_port}",
                )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
                status_code=502,
                detail=f"Reverse proxy unreachable while deploying '{name}': {e}",
                )

    req = AddAAAARequest(name=host_name, ip=str(cep.ip))
    try:
        add_host_to_dns(req)
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"DNS service unreachable while deploying '{name}': {e}",
                )

    network_record.apps[name] = AppRecord(name=name, ip=cep.ip)
    save_db(network_store)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.get("/debugUpProxy")
def _debug_up_proxy(name: str):
    resp = client.get("/debugUp", params={"name": name})

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.get("/listUpProxy")
def _list_up_proxy():
    resp = client.get("list")

    return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp.headers,
        )

#NOTE: still gets time outs despite async def debug later
@apps_router.delete("/targetedDestroyProxy")
async def _targeted_destroy_proxy(name: str, network_name: str):
    network_store = load_db()
    network_record = network_store.networks.get(network_name)

    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{network_name}' not found",
                )

    if name not in network_record.apps:
        raise HTTPException(
                status_code=404,
                detail=f"App '{name}' is not deployed in network '{network_name}'",
                )

    cep = network_record.get_cep()
    if cep is None:
        raise HTTPException(
                status_code=409,
                detail=(
                    f"Network '{network_name}' has no cep host; cannot resolve "
                    f"the hostname of app '{name}'"
                    ),
                )
    host_name = f"{name}.{cep.name}.{network_name}"

    try:
        resp = client.delete("/targetedDestroy", params={"name": name})
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"Appstore unreachable while destroying '{name}': {e}",
                )
    if resp.is_error:
        raise _appstore_error(resp, f"Appstore destroy of '{name}' failed")

    try:
        CaddyReverseProxy.remove_rproxy(hostname=host_name)
    except requests.exceptions.RequestException as e:
        raise HTTPException(
                status_code=502,
                detail=f"Reverse proxy unreachable while destroying '{name}': {e}",
                )

    try:
        remove_host_from_dns(host_name)
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"DNS service unreachable while destroying '{name}': {e}",
                )

    del network_record.apps[name]
    save_db(network_store)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.delete("/clearProxy")
async def _delete_proxy():
    resp = client.delete("/clear")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )