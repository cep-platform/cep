import typer

from cep.cli.storage.pool import pool_app
from cep.cli.storage.volume import volume_app

storage_app = typer.Typer()
storage_app.add_typer(pool_app, name='pool')
storage_app.add_typer(volume_app, name='volume')
