from fastapi import APIRouter, Response
import httpx

apps_router = APIRouter(prefix="/apps")

client = httpx.Client(base_url="http://localhost:8080")


@apps_router.post("/deploy")
def deploy(name: str):
    resp = client.post("/deploy", params={"name": name})
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )


@apps_router.get("/list")
def _list():
    resp = client.get("/list")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )
