import os

from typing import Optional
from fastapi import APIRouter, Response
import httpx
from fastapi.exceptions import HTTPException

from cep.apps.caddy import CaddyReverseProxy
from cep.datamodels import AppRecord
from cep.server.apps.store import store_router
from cep.server.dns import add_host_to_dns, AddAAAARequest
from cep.server.utils import load_db, save_db

from rich import print

apps_router = APIRouter(prefix="/apps")
apps_router.include_router(store_router)

hostname = os.environ.get("APP_STORE_HOST_NAME", "localhost")
client = httpx.Client(base_url=f"http://{hostname}:8080")


@apps_router.post("/deployProxy")
def deploy(name: str, network_name: str):
    network_store = load_db()
    network_record = network_store.networks.get(network_name)

    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{network_name}' not found",
                )

    if network_record.apps.get(name, False):
        raise HTTPException(
                status_code=409,
                detail=f"Host '{name}' already exists in network '{network_name}'",
                )

    cep = network_record.get_cep()
    host_name = f"{name}.{cep.name}.{network_name}"
    app_record = AppRecord(name=name, ip=cep.ip)
    network_record.apps[name] = app_record

    resp = client.post("/deploy", params={"name": name})
    CaddyReverseProxy.add_rproxy(
            hostname=host_name,
            destination=name
            )
    req = AddAAAARequest(name=host_name, ip=str(cep.ip))
    add_host_to_dns(req)

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
async def _targeted_destroy_proxy(name: str):
    resp = client.delete("/targetedDestroy", params={"name": name})
    CaddyReverseProxy.remove_rproxy(
            hostname=f"{name}.reverseproxy.cep",
            )
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
