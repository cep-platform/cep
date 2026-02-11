import os

from typing import Optional
from fastapi import APIRouter, Response
import httpx

store_router = APIRouter(prefix="/store")

hostname = os.environ.get("APP_STORE_HOST_NAME", "localhost")
client = httpx.Client(base_url=f"http://{hostname}:8080/store")

@store_router.get("/listProxy")
def _list_proxy():
    resp = client.get("/list")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )
