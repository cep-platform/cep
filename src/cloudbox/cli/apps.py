from typing import Optional
import typer
from rich import print
import uvicorn

from cloudbox.cli.utils import get_client, parse_available
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


#TODO: async loop
@app_store_app.command()
def deploy(name_arr: list[str]) -> str | None:
    for name in name_arr:
        resp = client.post("/deploy", params={'name': name})
        resp.raise_for_status()
        breakpoint()


@app_store_app.command("list-available")
def _list_available():
    resp = client.get("/listAvailable")
    resp.raise_for_status()
    apps = resp.json()
    if apps:
        print('\n'.join(apps))

@app_store_app.command("list-up")
def _list_up(verbose: Optional[bool]=typer.Argument(default=False)):
    resp = client.get("/listUp")
    resp.raise_for_status()
    apps = resp.json()
    if apps:
        parse_available(apps, verbose)

#TODO: Down/delete
@app_store_app.command()
def delete(name: str):
    raise NotImplementedError()
    resp = client.delete("/delete", params={'name': name})
    resp.raise_for_status()


@app_store_app.command()
def edit(name: str):
    raise NotImplementedError()
