from typing import Optional
import typer
from rich import print
import uvicorn

from cep.cli.utils import get_client, parse_available
app_store_app = typer.Typer()
client_proxy = get_client("/apps")


@app_store_app.command("run")
def run():
    ascii_banner = r"""
_________  _____________________        _____
\_   ___ \ \_   _____/\______   \      /  _  \  ______  ______   ______
/    \  \/  |    __)_  |     ___/     /  /_\  \ \____ \ \____ \ /  ___/
\     \____ |        \ |    |        /    |    \|  |_> >|  |_> >\___ \
 \______  //_______  / |____|        \____|__  /|   __/ |   __//____  >
        \/         \/                        \/ |__|    |__|        \/
    """
    print(ascii_banner)
    uvicorn.run(
        "cep.app_store.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )


#TODO: async loop
@app_store_app.command("deploy")
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

#TODO:
# - Debug == True runs ps needs to be parsed in some logging system
# - List up != list-available
#   - list available: what has been white-listed for your network
#   - list up: which of these "whitelisted" and deployed apps in the past are still up
#      - returns array of up apps where |up| <= |available|
#      - just read deployment path on list up
#      - i.e compose_services.services.keys() --> thats it
@app_store_app.command("debug-up")
def _debug_up(verbose: Optional[bool]=typer.Argument(default=False),
             name: Optional[str]=typer.Argument(default=None)  
             ):
    """
    Wrapper on ps command for debugging, returns entire output
    if verbose=True, returns only age, image name and size otherwise

    Only useful to debug if local config is suspected to be inconsistent
    """

    resp = client_proxy.get("/debugUpProxy", params={"name": name})

    resp.raise_for_status()
    apps = resp.json()

    if apps:
        parse_available(apps, verbose)
    else:
        print("No apps running, run deploy to deploy some")

@app_store_app.command("list-up")
def _list_up():
    """
    Reads config to check which apps are running,
        Might be inconsistent, when in doubt run debug-up
    """
    resp = client_proxy.get("/listUpProxy")
    resp.raise_for_status()
    print("Apps up: \n", resp.content)

@app_store_app.command("targeted-destroy")
def _targeted_destroy(name_arr: list[str]):
    """
    Unlike clear, this applies compose down *ONLY* on selected apps
    is async but time-out errors occur need to check whats up with that
    """
    for name in name_arr:
        resp = client_proxy.delete("/targetedDestroyProxy", params={'name': name})
        resp.raise_for_status()

#TODO: async + with docker compose for all apps
@app_store_app.command("clear")
def _clear():
    """
    Downs all apps
    """
    resp = client_proxy.delete("/clearProxy")
    resp.raise_for_status()
