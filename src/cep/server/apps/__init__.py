from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Depends, Response
import httpx
from fastapi.exceptions import HTTPException
import requests

from cep.apps.main import AppInstallRequest
from cep.apps.caddy import CaddyReverseProxy
from cep.apps.incus import PROXY_PORT_LABEL
from cep.datamodels import AppRecord, AddAAAARequest, HostRecord, NetworkStore
from cep.server.apps.store import store_router
from cep.server.dns import add_host_to_dns, remove_host_from_dns
from cep.server.db import (
    get_network_store,
    get_network_store_write,
    load_db,
    save_db,
)

apps_router = APIRouter(prefix="/apps")
apps_router.include_router(store_router)

hostname = os.environ.get("APP_STORE_HOST_NAME", "localhost")
client = httpx.Client(base_url=f"http://{hostname}:8080")

LOGGER = logging.getLogger(__name__)

# Poll cadence for appstore install jobs. Every single HTTP call is short
# (the appstore answers instantly); what is slow is the incus-compose work
# behind the job. Keep the CLI deploy timeout above DEPLOY_POLL_TIMEOUT so
# the server's actionable 504 beats the client's read timeout.
DEPLOY_POLL_INTERVAL = 2.0
DEPLOY_POLL_TIMEOUT = 600.0


def _appstore_error(resp: httpx.Response, fallback: str) -> HTTPException:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = None
    return HTTPException(
            status_code=resp.status_code,
            detail=str(detail) if detail else fallback,
            )


def _deployed_service(template: dict, name: str) -> dict:
    services = template.get("services", {})
    if len(services) != 1:
        raise HTTPException(
                status_code=500,
                detail=(
                    f"App template '{name}' must define exactly one service, "
                    f"got {len(services)}"
                    ),
                )
    return next(iter(services.values()))


def _poll_appstore_job(job_id: str, name: str) -> dict:
    """
    Poll the appstore install job until it leaves the running state.

    Returns the job body (state=done, result=app template). Raises 502 when
    the appstore is unreachable or the job failed, 504 when the job is
    still running after DEPLOY_POLL_TIMEOUT seconds.
    """
    deadline = time.monotonic() + DEPLOY_POLL_TIMEOUT
    while True:
        try:
            resp = client.get(f"/jobs/{job_id}")
        except httpx.HTTPError as e:
            raise HTTPException(
                    status_code=502,
                    detail=f"Appstore unreachable while deploying '{name}': {e}",
                    )
        if resp.is_error:
            raise _appstore_error(resp, f"Appstore deploy of '{name}' failed")
        job = resp.json()
        state = job.get("state")
        LOGGER.debug("deployProxy: job %s state=%s", job_id, state)
        if state == "done":
            return job
        if state == "failed":
            detail = job.get("error") or "no error reported"
            raise HTTPException(
                    status_code=502,
                    detail=f"Appstore deploy of '{name}' failed: {detail}",
                    )
        if time.monotonic() >= deadline:
            raise HTTPException(
                    status_code=504,
                    detail=(
                        f"Deploy of '{name}' did not finish within "
                        f"{DEPLOY_POLL_TIMEOUT}s; the app may still be "
                        "starting - check the appstore logs and retry "
                        "once it is up"
                        ),
                    )
        time.sleep(DEPLOY_POLL_INTERVAL)


def _finalize_deploy(
        network_name: str,
        name: str,
        cep: HostRecord,
        ) -> None:
    """
    Record the deployed app in the network store.

    Deliberately not get_network_store_write: that dependency holds the
    BEGIN IMMEDIATE write transaction for the whole request, and this
    request polls the appstore for minutes - that would block every other
    mutating endpoint (WAL readers are unaffected). Validation ran on a
    read snapshot; the bare load_db()/save_db() pair here is atomic per
    call but not across the pair, so the 404/409 checks are repeated to
    close the practical race.
    """
    store = load_db()
    network_record = store.networks.get(network_name)
    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{network_name}' not found",
                )
    if name in network_record.apps:
        raise HTTPException(
                status_code=409,
                detail=f"App '{name}' is already deployed in network '{network_name}'",
                )
    network_record.apps[name] = AppRecord(name=name, ip=cep.ip)
    save_db(store)


@apps_router.post("/deployProxy")
def deploy(name: str,
           network_name: str,
           network_store: NetworkStore = Depends(get_network_store),
           ):
    """
    Deploy an app on the network's cep host via the appstore.

    Read-only dependency on purpose (see _finalize_deploy): this request
    polls the appstore's install job for up to DEPLOY_POLL_TIMEOUT.
    """
    LOGGER.debug(
        "deployProxy: deploying app %r on network %r (known networks: %s)",
        name,
        network_name,
        ", ".join(sorted(network_store.networks)) or "<none>",
    )
    network_record = network_store.networks.get(network_name)

    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{network_name}' not found",
                )

    LOGGER.debug(
        "deployProxy: network %r state: apps=%s hosts=%s",
        network_name,
        sorted(network_record.apps),
        sorted(network_record.hosts),
    )
    if name in network_record.apps:
        raise HTTPException(
                status_code=409,
                detail=f"App '{name}' is already deployed in network '{network_name}'",
                )

    cep = network_record.get_cep()
    if cep is None:
        raise HTTPException(
                status_code=409,
                detail=(
                    f"Network '{network_name}' has no cep host; create the "
                    "network's first host before deploying apps"
                    ),
                )
    host_name = f"{name}.{cep.name}.{network_name}"

    install_params = AppInstallRequest(id=name).model_dump()
    LOGGER.debug(
        "deployProxy: appstore install: POST %s body=%s",
        client.base_url,
        install_params,
    )
    try:
        resp = client.post("/", json=install_params)
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"Appstore unreachable while deploying '{name}': {e}",
                )
    LOGGER.debug(
        "deployProxy: appstore accepted: HTTP %s body=%r",
        resp.status_code,
        resp.text,
    )
    if resp.is_error:
        raise _appstore_error(resp, f"Appstore deploy of '{name}' failed")

    try:
        job_id = resp.json().get("job_id")
    except ValueError:
        job_id = None
    if not job_id:
        raise HTTPException(
                status_code=500,
                detail=f"Appstore deploy of '{name}' returned no job id",
                )

    job = _poll_appstore_job(job_id, name)
    template = job.get("result")
    if not template:
        raise HTTPException(
                status_code=500,
                detail=f"Appstore deploy of '{name}' returned no app template",
                )

    service = _deployed_service(template, name)
    container_name = service.get("container_name")
    rproxy_port = (service.get("labels") or {}).get(PROXY_PORT_LABEL)
    if not container_name or not rproxy_port:
        raise HTTPException(
                status_code=500,
                detail=(
                    f"App template '{name}' must define 'container_name' and "
                    f"the '{PROXY_PORT_LABEL}' label"
                    ),
                )

    try:
        CaddyReverseProxy.add_rproxy(
                hostname=host_name,
                destination=f"{container_name}:{rproxy_port}",
                )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
                status_code=502,
                detail=f"Reverse proxy unreachable while deploying '{name}': {e}",
                )

    req = AddAAAARequest(name=host_name, ip=str(cep.ip))
    try:
        add_host_to_dns(req)
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"DNS service unreachable while deploying '{name}': {e}",
                )

    _finalize_deploy(network_name=network_name, name=name, cep=cep)
    LOGGER.debug(
        "deployProxy: deployed %r in network %r (hostname=%s, backend=%s:%s)",
        name,
        network_name,
        host_name,
        container_name,
        rproxy_port,
    )
    return template


@apps_router.get("/listUpProxy")
def _list_up_proxy():
    resp = client.get("/")

    return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp.headers,
        )


# NOTE: still gets time outs despite async def debug later
@apps_router.delete("/targetedDestroyProxy")
async def _targeted_destroy_proxy(
        name: str,
        network_name: str,
        network_store: NetworkStore = Depends(get_network_store_write),
        ):
    network_record = network_store.networks.get(network_name)

    if not network_record:
        raise HTTPException(
                status_code=404,
                detail=f"Network '{network_name}' not found",
                )

    if name not in network_record.apps:
        raise HTTPException(
                status_code=404,
                detail=f"App '{name}' is not deployed in network '{network_name}'",
                )

    cep = network_record.get_cep()
    if cep is None:
        raise HTTPException(
                status_code=409,
                detail=(
                    f"Network '{network_name}' has no cep host; cannot resolve "
                    f"the hostname of app '{name}'"
                    ),
                )
    host_name = f"{name}.{cep.name}.{network_name}"


    try:
        resp = client.delete(f"/{name}")
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"Appstore unreachable while destroying '{name}': {e}",
                )
    if resp.is_error:
        raise _appstore_error(resp, f"Appstore destroy of '{name}' failed")

    try:
        CaddyReverseProxy.remove_rproxy(hostname=host_name)
    except requests.exceptions.RequestException as e:
        raise HTTPException(
                status_code=502,
                detail=f"Reverse proxy unreachable while destroying '{name}': {e}",
                )

    try:
        remove_host_from_dns(host_name)
    except httpx.HTTPError as e:
        raise HTTPException(
                status_code=502,
                detail=f"DNS service unreachable while destroying '{name}': {e}",
                )

    del network_record.apps[name]
    return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp.headers,
            )
