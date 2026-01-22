import os

from fastapi import APIRouter, Response
import httpx

apps_router = APIRouter(prefix="/apps")

hostname = os.environ.get("APP_STORE_HOST_NAME", "localhost")
client = httpx.Client(base_url=f"http://{hostname}:8080")


@apps_router.post("/deploy")
def deploy(name: str):
    resp = client.post("/deploy", params={"name": name})
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.get("/listAvailable")
def _list_available():
    resp = client.get("/listAvailable")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.get("/listUp")
def _list_up():
    resp = client.get("/listUp")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )
