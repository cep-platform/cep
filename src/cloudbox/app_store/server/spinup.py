from fastapi import APIRouter
from cloudbox.app_store.server.utils import fetch_image_configs

from cloudbox.datamodels import AppStoreSpinupReport, AppStoreSpinupRequest, Container

import subprocess

app_spinup_router = APIRouter(prefix="/appStore/spinUp")

@app_spinup_router.post("/deploy")
def deploy(payload: AppStoreSpinupRequest) -> AppStoreSpinupReport | str:
    breakpoint() 
    #TODO: conform for list of apps
    # - make async
    app_name = payload.image_path
    command = fetch_image_configs(app_name)
    if command.is_err():
        print("Encountered err: ", command)
        return "Nooooo needs to send back report"

    command = command.ok()

    result = subprocess.run(
        [
            "docker-compose",
            "-f",
            command,
            "up"
        ],
        capture_output=True,
        text=True,
    )  # do we need to hold the py process while its pulling? I think this should be async

    print(f"{app_name} successfuly spin up: {result.stderr}")

    container = [Container(
        version=1,
        nusers=2,
        already_up=False
    )]
    app_store_report: AppStoreSpinupReport = AppStoreSpinupReport(
        image_path=app_name,
        container_list=container
    )
    return app_store_report
