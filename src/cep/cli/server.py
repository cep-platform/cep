from __future__ import annotations

import typer
import uvicorn

from cep.cli.utils import uvicorn_log_config

server_app = typer.Typer(help="server")


@server_app.command()
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
_________  _____________________        _____           .__
\_   ___ \ \_   _____/\______   \      /     \  _____   |__|  ____
/    \  \/  |    __)_  |     ___/     /  \ /  \ \__  \  |  | /    \
\     \____ |        \ |    |        /    Y    \ / __ \_|  ||   |  \
 \______  //_______  / |____|        \____|__  /(____  /|__||___|  /
        \/         \/                        \/      \/          \/
    """
    print(ascii_banner)

    log_level = log_level.lower()
    try:
        log_config = uvicorn_log_config(log_level)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e

    uvicorn.run(
        "cep.server.main:app",  # module:variable
        host="0.0.0.0",
        port=8000,
        reload=True,     # dev only
        log_level=log_level,
        log_config=log_config,
    )
