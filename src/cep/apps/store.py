from fastapi import APIRouter

from cep.apps.spec import list_presets

store_router = APIRouter(prefix="/store")


@store_router.get("/health")
def health():
    return "ok"


@store_router.get("/list")
def _list() -> list[str]:
    return list_presets()
