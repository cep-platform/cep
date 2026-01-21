import typer
from rich import print
import uvicorn

from cloudbox.cli.utils import get_client

app_store_app = typer.Typer()
client = get_client("/apps")


@app_store_app.command("run")
def run():
    uvicorn.run(
        "cloudbox.app_store.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )


@app_store_app.command()
def deploy(name: str) -> str | None:
    resp = client.post("/deploy", params={'name': name})
    resp.raise_for_status()


@app_store_app.command("list")
def _list():
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
