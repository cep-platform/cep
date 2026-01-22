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

@apps_router.get("/listUpProxy")
def _list_up_proxy():
    resp = client.get("/listUp")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.post("/stopProxy")
def _stop_proxy(name: str):
    resp = client.post("/stop", params={"name": name})
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )

@apps_router.delete("/deleteProxy")
def _delete_proxy(name: str):
    resp = client.delete("/delete", params={'name': name})
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )
