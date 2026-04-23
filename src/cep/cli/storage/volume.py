import typer
from rich import print

from cep.cli.utils import get_client

volume_app = typer.Typer()

client = get_client("/storage/volumes")


@volume_app.command('create')
def create(pool_name: str, name: str):
    resp = client.post("/create", params={'pool_name': pool_name, 'name': name})
    if resp.status_code == 200:
        print(f"Volume '{name}' created in pool '{pool_name}'")
    else:
        print(f"[red]Error:[/red] {resp.json().get('detail', resp.text)}")


@volume_app.command('delete')
def delete(pool_name: str, name: str):
    resp = client.delete("/delete", params={'pool_name': pool_name, 'name': name})
    if resp.status_code == 200:
        print(f"Volume '{name}' deleted from pool '{pool_name}'")
    else:
        print(f"[red]Error:[/red] {resp.json().get('detail', resp.text)}")


@volume_app.command('list')
def _list(pool_name: str | None = None):
    params = {}
    if pool_name:
        params['pool_name'] = pool_name
    resp = client.get("", params=params)
    resp.raise_for_status()
    volumes = resp.json()
    if not volumes:
        print("No volumes found")
        return
    for v in volumes:
        print(f"{v['pool_name']}/{v['name']} -> {v.get('host_path', 'N/A')}")


@volume_app.command('show')
def show(pool_name: str, name: str):
    resp = client.get("/show", params={'pool_name': pool_name, 'name': name})
    if resp.status_code != 200:
        print(f"[red]Error:[/red] {resp.json().get('detail', resp.text)}")
        return
    info = resp.json()
    print(f"Volume: {info['name']}")
    print(f"Pool: {info['pool_name']}")
    print(f"Host path: {info.get('host_path', 'N/A')}")
    print(f"Size: {info.get('total_size_bytes', '?')} bytes")
    print(f"Created: {info.get('created_at', 'N/A')}")
