from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from cep.apps.runtime import CommandFailed, Runtime, get_runtime
from cep.apps.spec import AppSpec, AppStatus, DeployRequest, InvalidSpec, resolve
from cep.apps.store import store_router
from cep.storage.docker import Pool, Volume, list_pools, list_all_volumes

app = FastAPI()
app.include_router(store_router)


@app.exception_handler(InvalidSpec)
def _invalid_spec(_: Request, e: InvalidSpec):
    return JSONResponse(status_code=422, content={"detail": str(e)})


@app.exception_handler(CommandFailed)
def _command_failed(_: Request, e: CommandFailed):
    return JSONResponse(status_code=500, content={"detail": e.stderr})


@app.get("/health")
def health():
    """Liveness check; always returns "ok"."""
    return "ok"


@app.post("/deploy")
def _deploy(req: DeployRequest, runtime: Runtime = Depends(get_runtime)) -> AppSpec:
    """Deploy a preset or any image ref (with optional overrides); returns the deployed spec."""
    spec = resolve(req)
    runtime.deploy(spec)
    return spec


@app.get("/list")
def _list(runtime: Runtime = Depends(get_runtime)) -> list[AppStatus]:
    """Apps deployed through the app store, with their live state."""
    return runtime.list()


@app.delete("/targetedDestroy")
def _destroy(name: str, runtime: Runtime = Depends(get_runtime)):
    """Destroy one app. 404 for anything the app store did not deploy."""
    if name not in {a.name for a in runtime.list()}:
        raise HTTPException(status_code=404, detail=f"no app named '{name}'")
    runtime.destroy(name)


@app.delete("/clear")
def _clear(runtime: Runtime = Depends(get_runtime)) -> list[str]:
    """Destroy every app deployed through the app store; returns their names."""
    names = [a.name for a in runtime.list()]
    for name in names:
        runtime.destroy(name)
    return names


# ---------------------------------------------------------------------------
# Storage endpoints - filesystem operations on host bind mount
# ---------------------------------------------------------------------------


@app.get("/storage/pools")
def storage_list_pools():
    return list_pools()


@app.post("/storage/pools/create")
def storage_create_pool(name: str):
    try:
        result = Pool(name).create()
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/storage/pools/delete")
def storage_delete_pool(name: str):
    try:
        Pool(name).delete()
        return {"status": "deleted", "name": name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/storage/pools/stats")
def storage_pool_stats(name: str):
    try:
        return Pool(name).get_stats()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/storage/volumes")
def storage_list_volumes(pool_name: Optional[str] = None):
    if pool_name:
        try:
            return Pool(pool_name).list_volumes()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    return list_all_volumes()


@app.post("/storage/volumes/create")
def storage_create_volume(pool_name: str, name: str):
    try:
        result = Volume(pool_name, name).create()
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/storage/volumes/delete")
def storage_delete_volume(pool_name: str, name: str):
    try:
        Volume(pool_name, name).delete()
        return {"status": "deleted", "pool_name": pool_name, "name": name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/storage/volumes/stats")
def storage_volume_stats(pool_name: str, name: str):
    try:
        return Volume(pool_name, name).info()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

