import typer
from rich import print

from cep.cli.utils import get_client

pool_app = typer.Typer()

client = get_client("/storage/pools")


@pool_app.command('create')
def create(name: str):
    resp = client.post("/create", params={'name': name})
    if resp.status_code == 200:
        print(f"Pool '{name}' created")
    else:
        print(f"[red]Error:[/red] {resp.json().get('detail', resp.text)}")


@pool_app.command('delete')
def delete(name: str):
    resp = client.delete("/delete", params={'name': name})
    if resp.status_code == 200:
        print(f"Pool '{name}' deleted")
    else:
        print(f"[red]Error:[/red] {resp.json().get('detail', resp.text)}")


@pool_app.command('list')
def _list():
    resp = client.get("")
    resp.raise_for_status()
    pools = resp.json()
    if not pools:
        print("No pools found")
        return
    for p in pools:
        print(f"{p['name']}: {p.get('volume_count', '?')} volumes, {p.get('total_size_bytes', '?')} bytes")


@pool_app.command('show')
def show(name: str):
    resp = client.get("/show", params={'name': name})
    if resp.status_code != 200:
        print(f"[red]Error:[/red] {resp.json().get('detail', resp.text)}")
        return
    stats = resp.json()
    print(f"Pool: {stats['name']}")
    print(f"Path: {stats.get('path', 'N/A')}")
    print(f"Volumes: {stats.get('volume_count', '?')}")
    print(f"Total size: {stats.get('total_size_bytes', '?')} bytes")
    print(f"Created: {stats.get('created_at', 'N/A')}")
