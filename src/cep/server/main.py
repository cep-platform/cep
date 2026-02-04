import os

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates

from cep.server.network import network_router
from cep.server.host import host_router
from cep.server.apps import apps_router
from cep.server.dns import dns_router
from cep.utils import JINJA_TEMPLATES_DIR

app = FastAPI()
templates = Jinja2Templates(directory=JINJA_TEMPLATES_DIR)


def instantiate_main_app():
    server_token = os.environ.get("CEP_SERVER_TOKEN", "")
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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "network/page.html",
        {
            "request": request,
            "name": "mom",
        },
    )
