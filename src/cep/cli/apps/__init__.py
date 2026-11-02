from typing import Annotated, Optional

import httpx
import typer
import uvicorn
from rich import print

from cep.apps.spec import DeployRequest, InvalidSpec, parse_env, parse_mount, parse_port
from cep.cli.apps.store import store_app
from cep.cli.utils import get_client

APP_OP_TIMEOUT = 600  # seconds; deploy blocks until the image is pulled

apps_app = typer.Typer()
apps_app.add_typer(store_app, name="store")

client_proxy = get_client("/apps")
client_proxy.timeout = httpx.Timeout(5, read=APP_OP_TIMEOUT)


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


def build_deploy_request(
    target: str,
    name: str | None,
    port: list[str],
    env: list[str],
    volume: list[str],
    privileged: bool,
) -> DeployRequest:
    """Flags left empty stay None, so they don't override a preset."""
    return DeployRequest(
        target=target,
        name=name,
        ports=[parse_port(p) for p in port] or None,
        env=dict(parse_env(e) for e in env) or None,
        mounts=[parse_mount(v) for v in volume] or None,
        privileged=privileged or None,
    )


def _check(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("detail", resp.text)
    except ValueError:
        detail = resp.text
    print(f"[red]Error {resp.status_code}:[/red] {detail}")
    raise typer.Exit(1)


@apps_app.command("deploy")
def _deploy(
    target: Annotated[str, typer.Argument(help="Preset name or image ref, e.g. redis or ghcr.io/foo/bar:1.0")],
    name: Annotated[Optional[str], typer.Option(help="App name (default: derived from the image)")] = None,
    port: Annotated[list[str], typer.Option(help="HOST:CONTAINER[/udp], repeatable")] = [],
    env: Annotated[list[str], typer.Option(help="KEY=VALUE, repeatable")] = [],
    volume: Annotated[list[str], typer.Option(help="SOURCE:TARGET[:ro], repeatable")] = [],
    privileged: Annotated[bool, typer.Option(help="Run the container privileged")] = False,
):
    """Deploy a preset or any OCI image."""
    try:
        req = build_deploy_request(target, name, port, env, volume, privileged)
    except InvalidSpec as e:
        print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    resp = client_proxy.post("/deployProxy", json=req.model_dump(exclude_none=True))
    _check(resp)
    print(f"Deployed {resp.json()['name']}")


@apps_app.command("list")
def _list():
    """Apps deployed through the app store, with their live state."""
    resp = client_proxy.get("/listUpProxy")
    _check(resp)
    for a in resp.json():
        preset = f"  [{a['preset']}]" if a.get("preset") else ""
        print(f"{a['name']}  {a['state']}  {a['image']}{preset}")


@apps_app.command()
def targeted_destroy(name_arr: list[str]):
    """Destroy the named apps."""
    for name in name_arr:
        _check(client_proxy.delete("/targetedDestroyProxy", params={"name": name}))


@apps_app.command()
def clear():
    """Destroy every app deployed through the app store."""
    resp = client_proxy.delete("/clearProxy")
    _check(resp)
    print("Destroyed:", ", ".join(resp.json()) or "nothing")
