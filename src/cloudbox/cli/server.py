import typer
from pathlib import Path

import uvicorn

CLOUDBOX_SERVER_CFG_PATH = Path('.cloudboxservercfg')

server_app = typer.Typer(help="server")


@server_app.command()
def set_auth_token(
    token: str = typer.Option(..., prompt=True, hide_input=True),
):
    """
    Store an authentication token for Cloudbox.
    """
    with open(CLOUDBOX_SERVER_CFG_PATH, 'w') as f:
        f.write(token)


@server_app.command()
def run():
    uvicorn.run(
        "cloudbox.server.main:app",  # module:variable
        host="0.0.0.0",
        port=8000,
        reload=True,     # dev only
    )
