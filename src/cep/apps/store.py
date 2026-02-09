from fastapi import APIRouter

from cep.apps.docker import Docker

store_router = APIRouter(prefix="/store")


@store_router.get("/health")
def health():
    return "ok"


@store_router.get("/list")
def _list() -> list[str]:
    return Docker.list_available_apps()
