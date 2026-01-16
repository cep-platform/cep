from fastapi import APIRouter, HTTPException
from datamodels import Container, AppStoreSpinupReport, AppStoreSpinupRequest
import subprocess

app_store_router = APIRouter(prefix="/appStore")


@app_store_router.post("/spinupAppStore")
def spinup_app_store(payload: AppStoreSpinupRequest) -> AppStoreSpinupReport:
    breakpoint() 
    
    subprocess.run(
        [
            "docker",
            "pull",
        ],
        capture_output=True,
        text=True,
    )

    container : Container = Container(
        application_list=["foo", "bar"],
        version="0.1",
        nusers=3,
    )
    app_store_report : AppStoreSpinupReport = AppStoreSpinupReport(
        image_path=payload.path,
        container_list=container
    )
    return app_store_report
