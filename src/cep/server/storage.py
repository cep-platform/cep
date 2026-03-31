from fastapi import APIRouter, HTTPException
from typing import Optional

from cep.storage.docker import (
    Pool,
    Volume,
    list_pools,
    list_all_volumes,
)

storage_router = APIRouter(prefix="/storage")


@storage_router.get("/pools")
def get_pools():
    return list_pools()


@storage_router.post("/pools/create")
def create_pool(name: str, path: Optional[str] = None):
    pool = Pool(name, path=path)
    try:
        pool.create()
        return {"status": "created", "name": name}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@storage_router.delete("/pools/delete")
def delete_pool(name: str):
    pool = Pool(name)
    try:
        pool.delete()
        return {"status": "deleted", "name": name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@storage_router.get("/pools/show")
def show_pool(name: str):
    pool = Pool(name)
    try:
        return pool.get_stats()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@storage_router.get("/volumes")
def get_volumes(pool_name: Optional[str] = None):
    if pool_name:
        pool = Pool(pool_name)
        try:
            return pool.list_volumes()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    return list_all_volumes()


@storage_router.post("/volumes/create")
def create_volume(pool_name: str, name: str):
    volume = Volume(pool_name, name)
    try:
        volume.create()
        return {"status": "created", "pool": pool_name, "name": name}
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@storage_router.delete("/volumes/delete")
def delete_volume(pool_name: str, name: str):
    volume = Volume(pool_name, name)
    try:
        volume.delete()
        return {"status": "deleted", "pool": pool_name, "name": name}
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@storage_router.get("/volumes/show")
def show_volume(pool_name: str, name: str):
    volume = Volume(pool_name, name)
    try:
        return volume.info()
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=404, detail=str(e))
