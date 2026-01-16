import typer
from rich import print

from typing import Dict
from cloudbox.cli.utils import get_client, CLI_DATA_DIR
from cloudbox.utils import get_available_path_templates, get_template_path
import subprocess
import yaml 

from result import Result, is_ok, is_err

app_store_app = typer.Typer()
client = get_client("/appStore")

from cloudbox.datamodels import (
    AppStoreMeshPrivileges,
    AppStoreSpinupReport,
    AppStoreSpinupRequest
)

def fetch_image_configs(app_name) -> Result[str, FileNotFoundError]:
    config_path =  get_available_path_templates(app_name)
    if config_path.is_err:
        return config_path
    return config_path

@app_store_app.command()
def spinup_app_store(app_name: str) -> str | None:
    """
    Pull an image from the following:
     - ubuntu
     - python
     - nginx:alpine
    Needs a path or token where to pull image(s) from
    """
    
    #TODO: Move all this server side when done
    #Also parse socket from yml back to here for ppl to ssh
    command = fetch_image_configs(app_name)
    
    if command.is_err():
        print("Encountered err: ", command)
        return

    command = command.ok()

    # req = AppStoreSpinupRequest(
    #    image_path=app_name,
    #     federated=False,
    #    privilege=AppStoreMeshPrivileges.EditStore
    # )
    #
    # resp = client.post("/spinupAppStore", 
    #                    json=req.model_dump(mode="json")
    # )
    
    # this causes a runtime error and kills python process if args are not parsed well no point in checking return value
    result = subprocess.run(
        [
            "docker-compose",
            "-f",
            command,
            "up",
            "-d"
        ],
        capture_output=True,
        text=True,
    ) #do we need to hold the py process while its pulling? I think this should be async
    print(f"{app_name} successfuly spin up: {result.stderr}")
    return

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
