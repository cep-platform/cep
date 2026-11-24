from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
import uvicorn
import yaml
from rich import print

from cep.apps.spec import DeployRequest, InvalidSpec, parse_env, parse_mount, parse_port
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


COMPOSE_SUFFIXES = (".yml", ".yaml")


def build_deploy_request(
    target: str,
    name: str | None,
    port: list[str],
    env: list[str],
    volume: list[str],
    privileged: bool,
    proxy_port: int | None,
) -> DeployRequest:
    """A TARGET ending in .yml/.yaml is a compose file to read; anything else
    is a preset or image ref. Flags left empty stay None, so they don't
    override a preset."""
    source = {"target": target}
    if target.endswith(COMPOSE_SUFFIXES):
        try:
            source = {"compose": yaml.safe_load(Path(target).read_text())}
        except (OSError, yaml.YAMLError) as e:
            raise InvalidSpec(f"cannot read compose file '{target}': {e}") from None
    return DeployRequest(
        **source,
        name=name,
        ports=[parse_port(p) for p in port] or None,
        env=dict(parse_env(e) for e in env) or None,
        mounts=[parse_mount(v) for v in volume] or None,
        privileged=privileged or None,
        proxy_port=proxy_port,
    )


def _exit_on_error(resp: httpx.Response) -> None:
    if not resp.is_error:
        return
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = None
    print(f"[red]Error {resp.status_code}:[/red] {detail or resp.text}")
    raise typer.Exit(1)


#TODO: async loop
@apps_app.command("deploy")
def _deploy(
    target: Annotated[str, typer.Argument(
        help="Preset (see `cep apps store list`), image ref (ghcr.io/foo/bar:1.0) "
             "or path to a compose file (.yml/.yaml)")],
    network_name: str,
    name: Annotated[Optional[str], typer.Option(help="App name (default: preset, image or routed service name)")] = None,
    port: Annotated[list[str], typer.Option(help="HOST:CONTAINER[/udp], repeatable")] = [],
    env: Annotated[list[str], typer.Option(help="KEY=VALUE, repeatable")] = [],
    volume: Annotated[list[str], typer.Option(help="SOURCE:TARGET[:ro], repeatable")] = [],
    privileged: Annotated[bool, typer.Option(help="Run the container privileged")] = False,
    proxy_port: Annotated[Optional[int], typer.Option(
        help="Container port the reverse proxy routes to (default: first --port)")] = None,
) -> None:
    """Deploy a preset, any OCI image, or your own compose file."""
    try:
        req = build_deploy_request(target, name, port, env, volume, privileged, proxy_port)
    except InvalidSpec as e:
        print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    print(
        f"Deploying [green]{target}[/green] on network "
        f"[green]{network_name}[/green] - this can take a few minutes"
    )
    resp = client_proxy.post(
            "/deployProxy",
            params={'network_name': network_name},
            json=req.model_dump(exclude_none=True),
            timeout=DEPLOY_TIMEOUT,
            )
    _exit_on_error(resp)


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
