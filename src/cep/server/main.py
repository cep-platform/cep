from __future__ import annotations

import os

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from cep.server.network import network_router
from cep.server.host import host_router
from cep.server.apps import apps_router
from cep.server.dns import dns_router


def instantiate_main_app():
    app = FastAPI()

    # Liveness probe for the incus-compose healthcheck (compose.yml). A 200
    # here is the HTTP equivalent of uvicorn's "Application startup
    # complete.": uvicorn serves no request before the lifespan startup
    # finishes, so this gates `incus-compose up` on real readiness. Keep it
    # side-effect free - the probe must never touch the appstore, DNS, or the
    # DB.
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
    # server_token = os.environ.get("CEP_SERVER_TOKEN", "")
    
    # if server_token:
    #
    #     def verify_token(
    #         credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    #     ):
    #         token = credentials.credentials
    #
    #         if token != server_token:
    #             raise HTTPException(
    #                 status_code=status.HTTP_401_UNAUTHORIZED,
    #                 detail="Invalid or missing token",
    #             )
    #     return FastAPI(
    #             dependencies=[Depends(verify_token)]
    #             )
    # else:
    #     return FastAPI()
    #

app = instantiate_main_app()
app.include_router(network_router)
app.include_router(host_router)
app.include_router(apps_router)
app.include_router(dns_router)
