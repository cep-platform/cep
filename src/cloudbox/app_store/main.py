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


@app.get("/list")
def _list() -> list[str]:
    return Docker.list_apps()
