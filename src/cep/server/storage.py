import os

from fastapi import APIRouter, HTTPException
from typing import Optional
import httpx

from cep.datamodels import PoolRecord, VolumeRecord
from cep.server.utils import load_storage_db, save_storage_db

storage_router = APIRouter(prefix="/storage")

hostname = os.environ.get("APP_STORE_HOST_NAME", "localhost")
client = httpx.Client(base_url=f"http://{hostname}:8080")


# ---------------------------------------------------------------------------
# Pool endpoints
# ---------------------------------------------------------------------------


@storage_router.get("/pools")
def get_pools():
    """List all pools from local metadata."""
    db = load_storage_db()
    return [pool.model_dump() for pool in db.pools.values()]


@storage_router.post("/pools/create")
def create_pool(name: str):
    """
    Create a pool: proxy filesystem creation to appstore,
    then persist metadata locally.
    """
    db = load_storage_db()
    if name in db.pools:
        raise HTTPException(status_code=409, detail=f"Pool '{name}' already exists")

    resp = client.post("/storage/pools/create", params={"name": name})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", resp.text))

    result = resp.json()
    db.pools[name] = PoolRecord(
        name=result["name"],
        path=result["path"],
        created_at=result["created_at"],
    )
    save_storage_db(db)
    return {"status": "created", "name": name}


@storage_router.delete("/pools/delete")
def delete_pool(name: str):
    """
    Delete a pool: proxy filesystem deletion to appstore,
    then remove metadata locally.
    """
    db = load_storage_db()
    if name not in db.pools:
        raise HTTPException(status_code=404, detail=f"Pool '{name}' does not exist")

    # Check that no volumes reference this pool
    pool_volumes = [v for v in db.volumes.values() if v.pool_name == name]
    if pool_volumes:
        raise HTTPException(
            status_code=409,
            detail=f"Pool '{name}' still has {len(pool_volumes)} volume(s)",
        )

    resp = client.delete("/storage/pools/delete", params={"name": name})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", resp.text))

    del db.pools[name]
    save_storage_db(db)
    return {"status": "deleted", "name": name}


@storage_router.get("/pools/show")
def show_pool(name: str):
    """
    Show pool info: metadata from local DB, live disk stats from appstore.
    """
    db = load_storage_db()
    if name not in db.pools:
        raise HTTPException(status_code=404, detail=f"Pool '{name}' does not exist")

    resp = client.get("/storage/pools/stats", params={"name": name})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", resp.text))

    stats = resp.json()
    pool_meta = db.pools[name].model_dump()
    pool_meta.update(stats)
    return pool_meta


# ---------------------------------------------------------------------------
# Volume endpoints
# ---------------------------------------------------------------------------


@storage_router.get("/volumes")
def get_volumes(pool_name: Optional[str] = None):
    """List volumes from local metadata, optionally filtered by pool."""
    db = load_storage_db()
    volumes = list(db.volumes.values())
    if pool_name:
        volumes = [v for v in volumes if v.pool_name == pool_name]
    return [v.model_dump() for v in volumes]


@storage_router.post("/volumes/create")
def create_volume(pool_name: str, name: str):
    """
    Create a volume: proxy directory creation to appstore,
    then persist metadata locally.
    """
    db = load_storage_db()
    if pool_name not in db.pools:
        raise HTTPException(status_code=404, detail=f"Pool '{pool_name}' does not exist")

    volume_key = f"{pool_name}/{name}"
    if volume_key in db.volumes:
        raise HTTPException(
            status_code=409,
            detail=f"Volume '{name}' already exists in pool '{pool_name}'",
        )

    resp = client.post(
        "/storage/volumes/create",
        params={"pool_name": pool_name, "name": name},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", resp.text))

    result = resp.json()
    db.volumes[volume_key] = VolumeRecord(
        name=result["name"],
        pool_name=result["pool_name"],
        host_path=result["host_path"],
        created_at=result["created_at"],
    )
    save_storage_db(db)
    return {"status": "created", "pool": pool_name, "name": name}


@storage_router.delete("/volumes/delete")
def delete_volume(pool_name: str, name: str):
    """
    Delete a volume: proxy directory removal to appstore,
    then remove metadata locally.
    """
    db = load_storage_db()
    volume_key = f"{pool_name}/{name}"
    if volume_key not in db.volumes:
        raise HTTPException(
            status_code=404,
            detail=f"Volume '{name}' does not exist in pool '{pool_name}'",
        )

    resp = client.delete(
        "/storage/volumes/delete",
        params={"pool_name": pool_name, "name": name},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", resp.text))

    del db.volumes[volume_key]
    save_storage_db(db)
    return {"status": "deleted", "pool": pool_name, "name": name}


@storage_router.get("/volumes/show")
def show_volume(pool_name: str, name: str):
    """
    Show volume info: metadata from local DB, live disk stats from appstore.
    """
    db = load_storage_db()
    volume_key = f"{pool_name}/{name}"
    if volume_key not in db.volumes:
        raise HTTPException(
            status_code=404,
            detail=f"Volume '{name}' does not exist in pool '{pool_name}'",
        )

    resp = client.get(
        "/storage/volumes/stats",
        params={"pool_name": pool_name, "name": name},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", resp.text))

    stats = resp.json()
    vol_meta = db.volumes[volume_key].model_dump()
    vol_meta.update(stats)
    return vol_meta
