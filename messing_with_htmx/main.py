from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import subprocess

app = FastAPI()
templates = Jinja2Templates(directory="templates")


def get_docker_containers():
    """
    Simple implementation using docker CLI.
    You could also use docker-py.
    """
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.ID}}|{{.Image}}|{{.Status}}|{{.Names}}"],
        capture_output=True,
        text=True,
    )
    print(result)

    containers = []
    for line in result.stdout.strip().splitlines():
        cid, image, status, name = line.split("|")
        containers.append(
            {
                "id": cid,
                "image": image,
                "status": status,
                "name": name,
            }
        )
    return containers


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    containers = get_docker_containers()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "containers": containers,
        },
    )


@app.get("/containers", response_class=HTMLResponse)
async def containers_partial(request: Request):
    """
    HTMX endpoint: returns ONLY the container list fragment
    """
    containers = get_docker_containers()
    return templates.TemplateResponse(
        "_containers.html",
        {
            "request": request,
            "containers": containers,
        },
    )

