import typer
from rich import print

from typing import Dict
from cloudbox.cli.utils import get_client, CLI_DATA_DIR
from cloudbox.utils import get_template_path
import subprocess
import yaml 

app_store_app = typer.Typer()
client = get_client("/appStore")

from cloudbox.datamodels import (
    AppStoreMeshPrivileges,
    AppStoreSpinupReport,
    AppStoreSpinupRequest
)

def fetch_image_configs() -> Dict[str, str]:
    config_path =  get_template_path("config.yml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config.get("AppStore").get("Images")

@app_store_app .command()
def spinup_app_store(image: str):
    """
    Pull an image from the following:
     - ubuntu
     - python
     - nginx:alpine
    Needs a path or token where to pull image(s) from
    """

    command_dict = fetch_image_configs()
    command = command_dict.get(image)
    
    subprocess.run(
        [
            "docker",
            "pull",
            command
        ],
        capture_output=True,
        text=True,
    )
    # #do we need to hold the py process while its pulling? I think this should be async
    
    # subprocess.run(
    #     [
    #         "docker",
    #         "images",
    #     ],
    #     capture_output=True,
    #     text=True,
    # )
    #
    # subprocess.run(
    #     [
    #         "docker",
    #         "run",
    #         "-it",
    #         command
    #     ],
    #     capture_output=True,
    #     text=True,
    # )
    #
    # req = AppStoreSpinupRequest(
    #    image_path=image,
    #     federated=False,
    #    privilege=AppStoreMeshPrivileges.EditStore
    # )
    #
    # resp = client.post("/spinupAppStore", 
    #                    json=req.model_dump(mode="json")
    # )
    #
    #
    # resp.raise_for_status()
    # print('\n'.join(resp.json()))
    #
    #
    # return

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
