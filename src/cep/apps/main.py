from typing import Optional
from fastapi import FastAPI
from cep.apps.docker import Docker
from cep.apps.store import store_router

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

