from fastapi import APIRouter

from cep.apps.incus import Incus

store_router = APIRouter(prefix="/store")


@store_router.get("/health")
def health():
    return "ok"


@store_router.get("/list")
def _list() -> list[str]:
    return Incus.list_available_apps()
