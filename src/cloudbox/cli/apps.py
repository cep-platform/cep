from typing import Optional
import typer
from rich import print
import uvicorn

from cloudbox.cli.utils import get_client, parse_available
app_store_app = typer.Typer()
client_proxy = get_client("/apps")


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
def _deploy(name_arr: list[str]) -> str | None:
    for name in name_arr:
        resp = client_proxy.post("/deployProxy", params={'name': name})
        resp.raise_for_status()


@app_store_app.command("list-available")
def _list_available():
    resp = client_proxy.get("/listAvailableProxy")
    resp.raise_for_status()
    apps = resp.json()
    if apps:
        print('\n'.join(apps))

@app_store_app.command("list-up")
def _list_up(verbose: Optional[bool]=typer.Argument(default=False)):
    resp = client_proxy.get("/listUpProxy")
    resp.raise_for_status()
    apps = resp.json()
    if apps:
        parse_available(apps, verbose)
    else:
        print("No apps running, run deploy to deploy some")

#TODO: async
@app_store_app.command("delete")
def _delete(name_arr: list[str]):
    resp = client_proxy.delete("/deleteProxy", params={'name': name_arr})
    resp.raise_for_status()

#TODO: async
@app_store_app.command("stop")
def _stop(name_arr: list[str]):
    for name in name_arr:
        resp = client_proxy.post("/stopProxy", params={'name': name})
        resp.raise_for_status()
