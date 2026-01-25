from typing import Optional
from fastapi import APIRouter, Response
import httpx

apps_router = APIRouter(prefix="/apps")

client = httpx.Client(base_url="http://localhost:8080")


@apps_router.post("/deployProxy")
def deploy(name: str):
    resp = client.post("/deploy", params={"name": name})
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.get("/listAvailableProxy")
def _list_available_proxy():
    resp = client.get("/listAvailable")
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
    resp = client.get("listUp")

    return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp.headers,
        )

#NOTE: still gets time outs despite async def debug later
@apps_router.delete("/targetedDestroyProxy")
async def _targeted_destroy_proxy(name: str):
    resp = client.delete("/targetedDestroy", params={"name": name})
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
