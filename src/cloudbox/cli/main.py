import json
import typer

from cloudbox.cli.apps import apps_app
from cloudbox.cli.host import host_app
from cloudbox.cli.network import network_app
from cloudbox.cli.server import server_app
from cloudbox.cli.utils import CLOUDBOXCFG_PATH


app = typer.Typer()
app.add_typer(network_app, name="network")
app.add_typer(host_app, name="host")
app.add_typer(server_app, name="server")
app.add_typer(apps_app, name="apps")


@app.command()
def auth():
    cloudbox_server_url = input("cloudbox server instance url: ")
    token = input("token: ")
    with open(CLOUDBOXCFG_PATH, 'w') as f:
        json.dump({
            'base_url': cloudbox_server_url,
            'token': token,
            }, f)
