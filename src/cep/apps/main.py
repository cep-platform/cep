import requests
from contextlib import asynccontextmanager
from time import sleep
from typing import Literal

from fastapi import FastAPI, Response
from pydantic import BaseModel, Field

from cep.apps.incus import Incus
from cep.apps.caddy import CaddyReverseProxy
from cep.apps.store import store_router


CADDY_INIT_ATTEMPTS = 3
CADDY_INIT_RETRY_DELAY = 9.0


def _init_caddy_with_retry() -> None:
    for attempt in range(1, CADDY_INIT_ATTEMPTS + 1):
        try:
            CaddyReverseProxy.ensure_initialized()
            return
        except requests.exceptions.RequestException:
            if attempt == CADDY_INIT_ATTEMPTS:
                raise
            sleep(CADDY_INIT_RETRY_DELAY)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_caddy_with_retry()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(store_router)


class AppInstallRequest(BaseModel):
    id: str
    config: dict[str, str] = Field(default_factory=dict)


class AppResponse(BaseModel):
    id: str
    desired: Literal["installed", "absent"]
    runtime: Literal[
        "running", "stopped", "partial", "missing", "unknown"
    ]
    operation: Literal["installing", "updating", "removing"] | None = None
    config: dict[str, str]


class AppListResponse(BaseModel):
    apps: list[AppResponse]


@app.get("", response_model=AppListResponse)
async def list_apps():
    return Incus.list_()


@app.get("/{app_id}", response_model=AppResponse)
async def get_app(app_id: str) -> AppResponse:
    return Incus.info(app_id=app_id)


@app.post("", response_model=AppResponse, status_code=201)
async def install_app(request: AppInstallRequest) -> AppResponse:
    app_template = Incus.get_app_template(request.id)
    Incus.add_to_deployment(request.id, app_template)
    Incus.compose_up(request.id)

    return app_template


@app.delete("/{app_id}", status_code=204)
async def uninstall_app(
    app_id: str,
    remove_data: bool = False,
) -> Response:
    Incus.compose_down(app_id=app_id)
    Incus.remove_from_deployment(app_id=app_id)
