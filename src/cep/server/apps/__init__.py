import os

from typing import Optional
from fastapi import APIRouter, Response
import httpx

from cep.apps.spec import DeployRequest

from cep.server.apps.store import store_router

apps_router = APIRouter(prefix="/apps")
apps_router.include_router(store_router)

hostname = os.environ.get("APP_STORE_HOST_NAME", "localhost")
# Deploy blocks until the image is pulled, so allow slow reads. Proxy handlers
# are sync `def` so FastAPI runs them in its threadpool instead of blocking the loop.
client = httpx.Client(base_url=f"http://{hostname}:8080", timeout=httpx.Timeout(5, read=600))


@apps_router.post("/deployProxy")
def deploy(req: DeployRequest):
    resp = client.post("/deploy", json=req.model_dump(exclude_none=True))
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.get("/listUpProxy")
def _list_up_proxy():
    resp = client.get("/list")

    return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp.headers,
        )

@apps_router.delete("/targetedDestroyProxy")
def _targeted_destroy_proxy(name: str):
    resp = client.delete("/targetedDestroy", params={"name": name})
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.delete("/clearProxy")
def _delete_proxy():
    resp = client.delete("/clear")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )
