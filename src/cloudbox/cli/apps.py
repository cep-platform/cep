import typer
from rich import print
import uvicorn

from typing import Dict
from cloudbox.cli.utils import get_apps_client
from cloudbox.utils import get_available_path_templates

from result import Result, is_ok, is_err

app_store_app = typer.Typer()
client = get_apps_client("/appStore")

from cloudbox.datamodels import (
    AppStoreMeshPrivileges,
    AppStoreSpinupRequest
)

@app_store_app.command("run")
def run():
    uvicorn.run(
        "cloudbox.app_store.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )

@app_store_app.command()
def spinup_app_store(app_name: str) -> str | None:
    """
    Pull an image from the following:
     - ubuntu
     - python
     - nginx:alpine
    Needs a path or token where to pull image(s) from
    """
    
    # TODO: parse socket from yml back to here for ppl to ssh
    

    req = AppStoreSpinupRequest(
       image_path=app_name,
        federated=False,
       privilege=AppStoreMeshPrivileges.EditStore
    )

    resp = client.post("/spinUp/deploy", 
                       json=req.model_dump(mode="json")
    )
    return resp


@app_store_app.command("list")
def _list():
    raise NotImplementedError()
    resp = client.get("/list")
    resp.raise_for_status()
    apps = resp.json()
    if apps:
        print('\n'.join(apps))


@app_store_app.command()
def create(name: str):
    raise NotImplementedError()
    resp = client.get("/create", params={'name': name})
    resp.raise_for_status()


@app_store_app.command()
def show(name: str):
    raise NotImplementedError()
    resp = client.get("/show", params={'name': name})
    resp.raise_for_status()
    print(resp.json())


@app_store_app.command()
def delete(name: str):
    raise NotImplementedError()
    resp = client.delete("/delete", params={'name': name})
    resp.raise_for_status()


@app_store_app.command()
def edit(name: str):
    raise NotImplementedError()


@app_store_app.command()
def deploy(name: str):
    raise NotImplementedError()
