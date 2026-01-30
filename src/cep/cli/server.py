import typer
import uvicorn

server_app = typer.Typer(help="server")


@server_app.command()
def run():
    ascii_banner = r"""
_________  _____________________        _____           .__
\_   ___ \ \_   _____/\______   \      /     \  _____   |__|  ____
/    \  \/  |    __)_  |     ___/     /  \ /  \ \__  \  |  | /    \
\     \____ |        \ |    |        /    Y    \ / __ \_|  ||   |  \
 \______  //_______  / |____|        \____|__  /(____  /|__||___|  /
        \/         \/                        \/      \/          \/
    """
    print(ascii_banner)
    uvicorn.run(
        "cep.server.main:app",  # module:variable
        host="0.0.0.0",
        port=8000,
        reload=True,     # dev only
    )
