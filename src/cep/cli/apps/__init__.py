from typing import Optional
import typer
from rich import print
import uvicorn

from cep.cli.utils import get_client, parse_available
from cep.cli.apps.store import store_app

apps_app = typer.Typer()
apps_app.add_typer(store_app, name="store")

client_proxy = get_client("/apps")


@apps_app.command()
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
        "cep.apps.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )


#TODO: async loop
@apps_app.command("deploy")
def _deploy(name_arr: list[str]) -> str | None:
    for name in name_arr:
        resp = client_proxy.post("/deployProxy", params={'name': name})
        resp.raise_for_status()


#TODO:
# - Debug == True runs ps needs to be parsed in some logging system
# - List up != list-available
#   - list available: what has been white-listed for your network
#   - list up: which of these "whitelisted" and deployed apps in the past are still up
#      - returns array of up apps where |up| <= |available|
#      - just read deployment path on list up
#      - i.e compose_services.services.keys() --> thats it
@apps_app.command()
def debug_up(verbose: Optional[bool]=typer.Argument(default=False),
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

@apps_app.command("list")
def _list():
    """
    Reads config to check which apps are running,
        Might be inconsistent, when in doubt run debug-up
    """
    resp = client_proxy.get("/listUpProxy")
    resp.raise_for_status()
    print("Apps up: \n", resp.content)

@apps_app.command()
def targeted_destroy(name_arr: list[str]):
    """
    Unlike clear, this applies compose down *ONLY* on selected apps
    is async but time-out errors occur need to check whats up with that
    """
    for name in name_arr:
        resp = client_proxy.delete("/targetedDestroyProxy", params={'name': name})
        resp.raise_for_status()

#TODO: async + with docker compose for all apps
@apps_app.command()
def clear():
    """
    Downs all apps
    """
    resp = client_proxy.delete("/clearProxy")
    resp.raise_for_status()
