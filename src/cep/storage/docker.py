import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_STORAGE_PATH = "/var/lib/cep/storage"
STORAGE_ROOT = Path(os.environ.get("CEP_STORAGE_PATH", DEFAULT_STORAGE_PATH))
POOLS_DIR = STORAGE_ROOT / "pools"


def ensure_storage_dirs() -> None:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    POOLS_DIR.mkdir(parents=True, exist_ok=True)


class Pool:
    def __init__(self, name: str, path: Optional[Path] = None):
        ensure_storage_dirs()
        self.name = name
        self.path = path or (POOLS_DIR / name)

    def exists(self) -> bool:
        return self.path.exists()

    def create(self) -> dict:
        if self.exists():
            raise ValueError(f"Pool '{self.name}' already exists")
        self.path.mkdir(parents=True, exist_ok=True)
        return {
            "name": self.name,
            "path": str(self.path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def delete(self) -> None:
        if not self.exists():
            raise ValueError(f"Pool '{self.name}' does not exist")
        if any(p for p in self.path.iterdir() if p.is_dir()):
            raise ValueError(f"Pool '{self.name}' is not empty")
        shutil.rmtree(self.path)

    def list_volumes(self) -> list[str]:
        if not self.exists():
            raise ValueError(f"Pool '{self.name}' does not exist")
        return [p.name for p in self.path.iterdir() if p.is_dir()]

    def get_stats(self) -> dict:
        if not self.exists():
            raise ValueError(f"Pool '{self.name}' does not exist")
        total_size = sum(
            d.stat().st_size for d in self.path.rglob("*") if d.is_file()
        )
        return {
            "name": self.name,
            "path": str(self.path),
            "volume_count": len(self.list_volumes()),
            "total_size_bytes": total_size,
        }


class Volume:
    def __init__(self, pool_name: str, name: str):
        ensure_storage_dirs()
        self.pool_name = pool_name
        self.name = name
        self.pool = Pool(pool_name)
        self.path = self.pool.path / name
        self.host_path = str(self.path)

    def create(self) -> dict:
        if not self.pool.exists():
            raise ValueError(f"Pool '{self.pool_name}' does not exist")
        if self.path.exists():
            raise ValueError(
                f"Volume '{self.name}' already exists in pool '{self.pool_name}'"
            )
        self.path.mkdir(parents=True, exist_ok=True)
        return {
            "name": self.name,
            "pool_name": self.pool_name,
            "host_path": self.host_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def delete(self) -> None:
        if not self.path.exists():
            raise ValueError(
                f"Volume '{self.name}' does not exist in pool '{self.pool_name}'"
            )
        shutil.rmtree(self.path)

    def info(self) -> dict:
        if not self.path.exists():
            raise ValueError(
                f"Volume '{self.name}' not found in pool '{self.pool_name}'"
            )
        total_size = sum(
            f.stat().st_size for f in self.path.rglob("*") if f.is_file()
        )
        created_at = datetime.fromtimestamp(
            self.path.stat().st_ctime, tz=timezone.utc
        ).isoformat()
        return {
            "name": self.name,
            "pool_name": self.pool_name,
            "host_path": self.host_path,
            "total_size_bytes": total_size,
            "created_at": created_at,
        }


def list_all_volumes() -> dict[str, list[str]]:
    ensure_storage_dirs()
    result = {}
    for pool_path in POOLS_DIR.iterdir():
        if pool_path.is_dir():
            result[pool_path.name] = [
                p.name for p in pool_path.iterdir() if p.is_dir()
            ]
    return result


def list_pools() -> list[dict]:
    ensure_storage_dirs()
    pools = []
    for pool_path in POOLS_DIR.iterdir():
        if pool_path.is_dir():
            pool = Pool(pool_path.name)
            pools.append(pool.get_stats())
    return pools
