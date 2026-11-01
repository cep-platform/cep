from __future__ import annotations

from typing import Optional
import typer
from rich import print
import uvicorn

from cep.cli.utils import get_client, parse_available, uvicorn_log_config
from cep.cli.apps.store import store_app

apps_app = typer.Typer()
apps_app.add_typer(store_app, name="store")

client_proxy = get_client("/apps")

# A bit above cep.server.apps.DEPLOY_POLL_TIMEOUT (600s) so the server's
# own actionable 504 beats the client's read timeout (see that module).
DEPLOY_TIMEOUT = 660.0


@apps_app.command()
def run(
    log_level: str = typer.Option(
        "info",
        "--log-level",
        "-l",
        help=(
            "Log level for uvicorn and app logging "
            "(critical|error|warning|info|debug|trace)."
        ),
    ),
):
    ascii_banner = r"""
_________  _____________________        _____
\_   ___ \ \_   _____/\______   \      /  _  \  ______  ______   ______
/    \  \/  |    __)_  |     ___/     /  /_\  \ \____ \ \____ \ /  ___/
\     \____ |        \ |    |        /    |    \|  |_> >|  |_> >\___ \
 \______  //_______  / |____|        \____|__  /|   __/ |   __//____  >
        \/         \/                        \/ |__|    |__|        \/
    """
    print(ascii_banner)

    log_level = log_level.lower()
    try:
        log_config = uvicorn_log_config(log_level)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e

    uvicorn.run(
        "cep.apps.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level=log_level,
        log_config=log_config,
    )


#TODO: async loop
@apps_app.command("deploy")
def _deploy(app_name: str, network_name: str) -> None:
    print(
        f"Deploying [green]{app_name}[/green] on network "
        f"[green]{network_name}[/green] - this can take a few minutes"
    )
    resp = client_proxy.post(
            "/deployProxy",
            params={
                'name': app_name,
                'network_name': network_name
                },
            timeout=DEPLOY_TIMEOUT,
            )
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
def targeted_destroy(network_name: str, name_arr: list[str]):
    """
    Unlike clear, this applies compose down *ONLY* on selected apps
    of the given network, also removing their reverse proxy and DNS records.
    Is async but time-out errors occur need to check whats up with that
    """
    for name in name_arr:
        resp = client_proxy.delete(
                "/targetedDestroyProxy",
                params={
                    'name': name,
                    'network_name': network_name,
                    })
        resp.raise_for_status()

#TODO: async + with docker compose for all apps
@apps_app.command()
def clear():
    """
    Downs all apps
    """
    resp = client_proxy.delete("/clearProxy")
    resp.raise_for_status()
