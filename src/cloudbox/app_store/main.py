from typing import Optional
from fastapi import FastAPI
from .docker import Docker

app = FastAPI()


@app.get("/health")
def health():
    return "ok"


@app.post("/deploy")
def deploy(name: str):
    app_template = Docker.get_app_template(name)
    Docker.add_to_deployment_file(app_template)
    Docker.compose_up()


@app.get("/listAvailable")
def _list_available() -> list[str]:
    return Docker.list_available_apps()


@app.get("/debugUp")
def _debug_up(name: str):
    return Docker.debug_up()

@app.get("/listUp")
def _list_up() -> list[str]:
    return Docker.list_up()


@app.delete("/targetedDestroy")
async def _targeted_destroy(name: str):
    return_code  = await Docker.targeted_destroy(name)
    if return_code == 0:
        Docker.update_deployment_file(name)

@app.delete("/clear")
async def _delete():
    return_code = await Docker.clear()
    if return_code == 0:
        Docker.clear_deployment_file()

