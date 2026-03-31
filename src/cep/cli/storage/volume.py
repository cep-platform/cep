import typer
from rich import print

from cep.storage.docker import Volume, list_all_volumes

volume_app = typer.Typer()


@volume_app.command('create')
def create(pool_name: str, name: str):
    volume = Volume(pool_name, name)
    try:
        volume.create()
        print(f"Volume '{name}' created in pool '{pool_name}'")
    except (ValueError, RuntimeError) as e:
        print(f"[red]Error:[/red] {e}")


@volume_app.command('delete')
def delete(pool_name: str, name: str):
    volume = Volume(pool_name, name)
    try:
        volume.delete()
        print(f"Volume '{name}' deleted from pool '{pool_name}'")
    except (ValueError, RuntimeError) as e:
        print(f"[red]Error:[/red] {e}")


@volume_app.command('list')
def _list(pool_name: str | None = None):
    if pool_name:
        from cep.storage.docker import Pool
        pool = Pool(pool_name)
        try:
            volumes = pool.list_volumes()
            if volumes:
                print('\n'.join(volumes))
            else:
                print(f"No volumes in pool '{pool_name}'")
        except ValueError as e:
            print(f"[red]Error:[/red] {e}")
    else:
        all_volumes = list_all_volumes()
        if not all_volumes:
            print("No volumes found")
            return
        for pool_name, volumes in all_volumes.items():
            if volumes:
                print(f"{pool_name}: {', '.join(volumes)}")
            else:
                print(f"{pool_name}: (empty)")


@volume_app.command('show')
def show(pool_name: str, name: str):
    volume = Volume(pool_name, name)
    try:
        info = volume.info()
        print(f"Name: {info['name']}")
        print(f"Pool: {info['pool_name']}")
        print(f"Docker name: {info['docker_name']}")
        print(f"Mountpoint: {info['mountpoint']}")
        print(f"Created: {info['created_at']}")
    except (ValueError, RuntimeError) as e:
        print(f"[red]Error:[/red] {e}")
