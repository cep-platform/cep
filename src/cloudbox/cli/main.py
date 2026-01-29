import typer
from dotenv import load_dotenv

from cloudbox.cli.apps import app_store_app
from cloudbox.cli.host import host_app
from cloudbox.cli.network import network_app
from cloudbox.cli.server import server_app
from cloudbox.cli.dns import dns_app

load_dotenv()


app = typer.Typer()
app.add_typer(network_app, name="network")
app.add_typer(host_app, name="host")
app.add_typer(server_app, name="server")
app.add_typer(dns_app, name="dns")
app.add_typer(app_store_app, name="apps")
