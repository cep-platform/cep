import typer
import uvicorn

server_app = typer.Typer(help="server")


@server_app.command()
def run():
    uvicorn.run(
        "cep.server.main:app",  # module:variable
        host="0.0.0.0",
        port=8000,
        reload=True,     # dev only
    )
