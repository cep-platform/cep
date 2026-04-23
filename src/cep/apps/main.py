from typing import Optional
from fastapi import FastAPI, HTTPException
from cep.apps.docker import Docker
from cep.apps.store import store_router
from cep.storage.docker import Pool, Volume, list_pools, list_all_volumes

app = FastAPI()
app.include_router(store_router)


@app.get("/health")
def health():
    """
    Health check endpoint.

    Returns a simple static response to indicate that the service
    is running and reachable.

    Returns:
        str: Always returns "ok" if the service is healthy.
    """
    return "ok"


@app.get("/debugUp")
def _debug_up(name: str):
    """
    Start a Docker service in debug mode.

    Brings up the specified application or service using a debug
    configuration. Intended for development and troubleshooting.

    Args:
        name (str): Name of the application or service to start in debug mode.

    Returns:
        Any: Result of the Docker.debug_up() operation.
    """
    return Docker.debug_up()


@app.get("/list")
def _list() -> list[str]:
    """
    List currently running Docker services.

    Retrieves a list of application or service names that are
    currently up according to Docker.

    Returns:
        list[str]: List of running application or service names.
    """
    return Docker.list_up()


@app.post("/deploy")
def _deploy(name: str):
    """
    Deploy an application using its Docker template.

    Fetches the application template, adds it to the deployment
    configuration, and brings up the Docker Compose stack.

    Args:
        name (str): Name of the application to deploy.

    Side Effects:
        - Updates the deployment file.
        - Runs `docker compose up` (or equivalent).
    """
    app_template = Docker.get_app_template(name)
    Docker.add_to_deployment_file(app_template)
    Docker.compose_up()


@app.delete("/targetedDestroy")
async def _destroy(name: str):
    """
    Destroy a specific deployed application or service.

    Stops and removes the specified application or service. If the
    operation succeeds, the deployment file is updated accordingly.

    Args:
        name (str): Name of the application or service to destroy.

    Side Effects:
        - Stops and removes targeted Docker resources.
        - Updates the deployment file on success.
    """
    return_code = await Docker.targeted_destroy(name)
    if return_code == 0:
        Docker.update_deployment_file(name)


@app.delete("/clear")
async def _delete():
    """
    Destroy all deployed applications and clear deployment state.

    Stops and removes all managed Docker services and clears the
    deployment configuration file if the operation succeeds.

    Side Effects:
        - Stops and removes all Docker resources managed by this service.
        - Clears the deployment file on success.
    """
    return_code = await Docker.clear()
    if return_code == 0:
        Docker.clear_deployment_file()


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

