import typer
from rich import print

from cep.storage.docker import Pool, list_pools

pool_app = typer.Typer()


@pool_app.command('create')
def create(name: str, path: str | None = None):
    pool = Pool(name, path=path)
    try:
        pool.create()
        print(f"Pool '{name}' created at {pool.path}")
    except ValueError as e:
        print(f"[red]Error:[/red] {e}")


@pool_app.command('delete')
def delete(name: str):
    pool = Pool(name)
    try:
        pool.delete()
        print(f"Pool '{name}' deleted")
    except ValueError as e:
        print(f"[red]Error:[/red] {e}")


@pool_app.command('list')
def _list():
    pools = list_pools()
    if not pools:
        print("No pools found")
        return
    for p in pools:
        print(f"{p['name']}: {p['volume_count']} volumes, {p['total_size_bytes']} bytes")


@pool_app.command('show')
def show(name: str):
    pool = Pool(name)
    try:
        stats = pool.get_stats()
        volumes = pool.list_volumes()
        print(f"Pool: {stats['name']}")
        print(f"Path: {stats['path']}")
        print(f"Volumes: {stats['volume_count']}")
        print(f"Total size: {stats['total_size_bytes']} bytes")
        if volumes:
            print(f"Volume list: {', '.join(volumes)}")
    except ValueError as e:
        print(f"[red]Error:[/red] {e}")
