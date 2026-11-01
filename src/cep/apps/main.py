from __future__ import annotations

import requests
from contextlib import asynccontextmanager
from enum import Enum
from time import sleep
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from cep.apps.incus import ComposeConfig, Incus
from cep.apps.caddy import CaddyReverseProxy
from cep.apps.store import store_router


CADDY_INIT_ATTEMPTS = 3
CADDY_INIT_RETRY_DELAY = 9.0


def _init_caddy_with_retry() -> None:
    for attempt in range(1, CADDY_INIT_ATTEMPTS + 1):
        try:
            CaddyReverseProxy.ensure_initialized()
            return
        except requests.exceptions.RequestException:
            if attempt == CADDY_INIT_ATTEMPTS:
                raise
            sleep(CADDY_INIT_RETRY_DELAY)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_caddy_with_retry()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(store_router)


class AppInstallRequest(BaseModel):
    id: str
    config: dict[str, str] = Field(default_factory=dict)


class JobState(str, Enum):
    """Lifecycle of an install job (POST / -> GET /jobs/{job_id})."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStatus(BaseModel):
    id: str
    state: JobState
    result: ComposeConfig | None = None
    error: str | None = None


class AppInstallAccepted(BaseModel):
    job_id: str
    status: JobState = JobState.RUNNING


# Install jobs live in memory only (single-worker appstore): a restart
# forgets running/done jobs and a client polling a forgotten job id gets a
# 404. Acceptable for Phase 1 - the deployed instances live in incus, not
# in this process.
JOBS: dict[str, JobStatus] = {}


def _run_install_job(
        job_id: str,
        app_id: str,
        app_template: ComposeConfig,
        ) -> None:
    """
    Background body of POST /: run the slow incus-compose deployment and
    record the outcome in JOBS. Must never raise - a failure is data
    (state=failed + error) so pollers can see it, not a server exception.
    """
    try:
        Incus.add_to_deployment(app_id, app_template)
        Incus.compose_up(app_id)
    except Exception as e:
        JOBS[job_id] = JobStatus(id=job_id, state=JobState.FAILED, error=str(e))
        return
    JOBS[job_id] = JobStatus(id=job_id, state=JobState.DONE, result=app_template)


# Liveness probe for the incus-compose healthcheck (compose.yml).
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def list_apps():
    return Incus.list_()


# Registered above the /{app_id} catch-all; known routes first is the
# safe default (see the /health regression note in the tests).
@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """Poll target for POST /: the job's state and, when done, the app
    template as result."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@app.get("/{app_id}")
async def get_app(app_id: str):
    return Incus.info(app_id=app_id)


@app.post("/", response_model=AppInstallAccepted, status_code=202)
async def install_app(
        request: AppInstallRequest,
        background_tasks: BackgroundTasks,
        ) -> AppInstallAccepted:
    """
    Async install: validate the template synchronously (fast 404 for an
    unknown app), then run the slow incus-compose deployment in a
    background task. Returns 202 + job_id immediately; poll
    GET /jobs/{job_id} until state is done (result = app template) or
    failed (error = reason).
    """
    try:
        app_template = Incus.get_app_template(request.id)
    except ValueError as e:
        # get_app_template's message names the template dir and lists the
        # available apps; surface it as an actionable 404, not a 500.
        raise HTTPException(status_code=404, detail=str(e))

    job_id = uuid4().hex
    JOBS[job_id] = JobStatus(id=job_id, state=JobState.RUNNING)
    # Sync task -> starlette runs it in the threadpool, so the blocking
    # incus-compose subprocess never blocks the event loop.
    background_tasks.add_task(_run_install_job, job_id, request.id, app_template)
    return AppInstallAccepted(job_id=job_id, status=JobState.RUNNING)


@app.delete("/{app_id}", status_code=204)
async def uninstall_app(
    app_id: str,
    remove_data: bool = False,
) -> Response:
    Incus.compose_down(app_id=app_id)
    Incus.remove_from_deployment(app_id=app_id)
    return Response(status_code=204)
