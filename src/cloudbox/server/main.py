from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from cloudbox.server.utils import CLOUDBOX_SERVER_CFG_PATH
from cloudbox.server.network import network_router
from cloudbox.server.host import host_router
from cloudbox.server.apps import apps_router


def instantiate_main_app():
    if CLOUDBOX_SERVER_CFG_PATH.exists():
        with open(CLOUDBOX_SERVER_CFG_PATH, 'r') as f:
            SERVER_TOKEN = f.read()

        def verify_token(
            credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
        ):
            token = credentials.credentials

            if token != SERVER_TOKEN:
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
