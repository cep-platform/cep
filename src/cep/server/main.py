from __future__ import annotations

from fastapi import FastAPI

from cep.server.network import network_router
from cep.server.host import host_router
from cep.server.apps import apps_router
from cep.server.dns import dns_router


def instantiate_main_app():
    app = FastAPI()

    # Liveness probe for the incus-compose healthcheck (compose.yml).
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = instantiate_main_app()
app.include_router(network_router)
app.include_router(host_router)
app.include_router(apps_router)
app.include_router(dns_router)
