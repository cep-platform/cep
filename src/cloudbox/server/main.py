import os

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from cloudbox.server.network import network_router
from cloudbox.server.host import host_router
from cloudbox.server.apps import apps_router
from cloudbox.server.dns import dns_router


def instantiate_main_app():
    server_token = os.environ.get("CLOUDBOX_SERVER_TOKEN", "")
    if server_token:

        def verify_token(
            credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
        ):
            token = credentials.credentials

            if token != server_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or missing token",
                )
        return FastAPI(
                dependencies=[Depends(verify_token)]
                )
    else:
        return FastAPI()


app = instantiate_main_app()
app.include_router(network_router)
app.include_router(host_router)
app.include_router(apps_router)
app.include_router(dns_router)
