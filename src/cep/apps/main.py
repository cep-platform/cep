from __future__ import annotations

import requests
from contextlib import asynccontextmanager
from time import sleep

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from cep.apps.incus import ComposeConfig, Incus
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


# Liveness probe for the incus-compose healthcheck (compose.yml)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def list_apps():
    return Incus.list_()


@app.get("/{app_id}")
async def get_app(app_id: str):
    return Incus.info(app_id=app_id)


@app.post("/", response_model=ComposeConfig, status_code=201)
async def install_app(request: AppInstallRequest) -> ComposeConfig:
    try:
        app_template = Incus.get_app_template(request.id)
    except ValueError as e:
        # get_app_template's message names the template dir and lists the
        # available apps; surface it as an actionable 404, not a 500.
        raise HTTPException(status_code=404, detail=str(e))
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
    return Response(status_code=204)
