import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from cep.utils import DATA_DIR

STORAGE_DATA_DIR = DATA_DIR / 'storage'
STORAGE_DATA_DIR.mkdir(exist_ok=True)

POOLS_DIR = STORAGE_DATA_DIR / 'pools'
POOLS_DIR.mkdir(exist_ok=True)


class Pool:
    def __init__(self, name: str, path: Optional[Path] = None):
        self.name = name
        self.path = path or (POOLS_DIR / name)

    def exists(self) -> bool:
        return self.path.exists()

    def create(self) -> None:
        if self.exists():
            raise ValueError(f"Pool '{self.name}' already exists")
        self.path.mkdir(parents=True, exist_ok=True)

    def delete(self) -> None:
        if not self.exists():
            raise ValueError(f"Pool '{self.name}' does not exist")
        if any(self.path.iterdir()):
            raise ValueError(f"Pool '{self.name}' is not empty")
        self.path.rmdir()

    def list_volumes(self) -> list[str]:
        if not self.exists():
            raise ValueError(f"Pool '{self.name}' does not exist")
        return [p.name for p in self.path.glob('*') if p.is_dir()]

    def get_stats(self) -> dict:
        if not self.exists():
            raise ValueError(f"Pool '{self.name}' does not exist")
        total_size = sum(
            d.stat().st_size for d in self.path.rglob('*') if d.is_file()
        )
        return {
            'name': self.name,
            'path': str(self.path),
            'volume_count': len(self.list_volumes()),
            'total_size_bytes': total_size,
        }


class Volume:
    def __init__(self, pool_name: str, name: str):
        self.pool_name = pool_name
        self.name = name
        self.pool = Pool(pool_name)
        self.docker_name = f"{pool_name}_{name}"
        self.path = self.pool.path / name

    def create(self) -> None:
        if not self.pool.exists():
            raise ValueError(f"Pool '{self.pool_name}' does not exist")
        if self.path.exists():
            raise ValueError(f"Volume '{self.name}' already exists in pool '{self.pool_name}'")

        result = subprocess.run(
            ['docker', 'volume', 'create', '--driver', 'local', self.docker_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create Docker volume: {result.stderr}")

        self.path.mkdir(parents=True, exist_ok=True)

    def delete(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)

        result = subprocess.run(
            ['docker', 'volume', 'rm', self.docker_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and 'no such volume' not in result.stderr.lower():
            raise RuntimeError(f"Failed to delete Docker volume: {result.stderr}")

    def info(self) -> dict:
        result = subprocess.run(
            ['docker', 'volume', 'inspect', self.docker_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(f"Volume '{self.name}' not found in pool '{self.pool_name}'")
        
        inspect_data = json.loads(result.stdout)[0]
        return {
            'name': self.name,
            'pool_name': self.pool_name,
            'docker_name': self.docker_name,
            'mountpoint': inspect_data.get('Mountpoint'),
            'created_at': inspect_data.get('CreatedAt'),
        }


def list_all_volumes() -> dict[str, list[str]]:
    result = {}
    for pool_path in POOLS_DIR.iterdir():
        if pool_path.is_dir():
            result[pool_path.name] = [
                p.name for p in pool_path.glob('*') if p.is_dir()
            ]
    return result


def list_pools() -> list[dict]:
    pools = []
    for pool_path in POOLS_DIR.iterdir():
        if pool_path.is_dir():
            pool = Pool(pool_path.name)
            pools.append(pool.get_stats())
    return pools
