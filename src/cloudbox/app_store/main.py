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


@app.get("/listUp")
def _list_up():
    return Docker.list_up()


@app.post("/stop")
def _stop(name: str):
    #TODO: utils to convert from app name to container name
    print(Docker.stop(name))


@app.delete("/delete")
def _delete(name: str):
    #TODO: utils to convert from app name to container name
    print(Docker.delete(name))
