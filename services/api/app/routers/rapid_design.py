import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from services.api.app.schemas.rapid_design import (
    MissionDemoJobRequest,
    MissionDemoJobResponse,
    MissionDemoProfile,
    RapidAnalyzeRequest,
    RapidAnalyzeResponse,
    RapidDesignJobResponse,
    RapidDesignRequest,
    RapidFamiliesResponse,
    RapidFamilyManifest,
)
from services.api.app.services.rapid_design.config_loader import (
    load_mission_demo_profile,
    load_rapid_design_config,
)
from services.api.app.services.rapid_design.families.registry import (
    UnknownFamilyError,
    registry,
)
from services.api.app.services.rapid_design.job_runner import (
    TERMINAL_STATUSES,
    RapidDesignJobRunner,
)
from services.api.app.services.rapid_design.mission_demo import MissionDemoRequestError
from services.api.app.services.rapid_design.mission_demo_job_runner import (
    MissionDemoJobRunner,
)

router = APIRouter(prefix="/api/rapid-design", tags=["rapid-design"])
runner = RapidDesignJobRunner()
demo_runner = MissionDemoJobRunner()


def _public_job(job: dict[str, object]) -> dict[str, object]:
    return {key: job[key] for key in RapidDesignJobResponse.model_fields}


def _public_demo_job(job: dict[str, object]) -> dict[str, object]:
    return {key: job[key] for key in MissionDemoJobResponse.model_fields}


def get_demo_runner() -> MissionDemoJobRunner:
    return demo_runner


DemoRunnerDependency = Annotated[MissionDemoJobRunner, Depends(get_demo_runner)]


@router.get("/config")
def get_config():
    return load_rapid_design_config().model_dump(mode="json")


@router.get("/demo/config", response_model=MissionDemoProfile)
def get_demo_config() -> MissionDemoProfile:
    return load_mission_demo_profile()


@router.get("/families", response_model=RapidFamiliesResponse)
def get_families() -> RapidFamiliesResponse:
    return RapidFamiliesResponse(families=registry.manifests())


@router.get("/families/{family_id}", response_model=RapidFamilyManifest)
def get_family(family_id: str) -> RapidFamilyManifest:
    try:
        return registry.manifest(family_id)
    except UnknownFamilyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/analyze", response_model=RapidAnalyzeResponse)
def analyze(request: RapidAnalyzeRequest) -> RapidAnalyzeResponse:
    try:
        return registry.analyze(request)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/jobs", status_code=202)
def create_job(request: RapidDesignRequest):
    try:
        return _public_job(runner.create(request.inputs))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _public_job(job)


async def _stream(job_id: str) -> AsyncIterator[str]:
    offset = 0
    while True:
        events = runner.events_since(job_id, offset)
        for event in events:
            offset += 1
            event_type = str(event["type"])
            yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        job = runner.get(job_id)
        if job is None or str(job["status"]) in TERMINAL_STATUSES:
            return
        if not events:
            yield ": keepalive\n\n"
        await asyncio.sleep(0.2)


@router.get("/jobs/{job_id}/events")
def stream_events(job_id: str):
    if runner.get(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return StreamingResponse(
        _stream(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}/result")
def get_result(job_id: str):
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    result = runner.result(job_id)
    if result is None:
        if job["status"] == "failed":
            raise HTTPException(status_code=500, detail=job["error"])
        raise HTTPException(status_code=409, detail="result is not ready")
    return result


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = runner.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _public_job(job)


@router.post(
    "/demo/jobs",
    status_code=202,
    response_model=MissionDemoJobResponse,
)
def create_demo_job(
    request: MissionDemoJobRequest,
    active_runner: DemoRunnerDependency,
) -> dict[str, object]:
    try:
        job = active_runner.create(
            family_id=request.family_id,
            preset_id=request.preset_id,
            supplied_inputs=request.inputs,
        )
    except MissionDemoRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail()) from exc
    return _public_demo_job(job)


@router.get("/demo/jobs/{job_id}", response_model=MissionDemoJobResponse)
def get_demo_job(
    job_id: str,
    active_runner: DemoRunnerDependency,
) -> dict[str, object]:
    job = active_runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="demo job not found")
    return _public_demo_job(job)


async def _stream_demo(
    job_id: str,
    active_runner: MissionDemoJobRunner,
) -> AsyncIterator[str]:
    offset = 0
    while True:
        events = active_runner.events_since(job_id, offset)
        for event in events:
            offset += 1
            event_type = str(event["type"])
            yield (
                f"event: {event_type}\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )
        job = active_runner.get(job_id)
        if job is None or str(job["status"]) in TERMINAL_STATUSES:
            return
        if not events:
            yield ": keepalive\n\n"
        await asyncio.sleep(0.2)


@router.get("/demo/jobs/{job_id}/events")
def stream_demo_events(
    job_id: str,
    active_runner: DemoRunnerDependency,
) -> StreamingResponse:
    if active_runner.get(job_id) is None:
        raise HTTPException(status_code=404, detail="demo job not found")
    return StreamingResponse(
        _stream_demo(job_id, active_runner),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/demo/jobs/{job_id}/result")
def get_demo_result(
    job_id: str,
    active_runner: DemoRunnerDependency,
) -> dict[str, object]:
    job = active_runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="demo job not found")
    result = active_runner.result(job_id)
    if result is None:
        if job["status"] == "failed":
            raise HTTPException(status_code=500, detail=job["error"])
        raise HTTPException(status_code=409, detail="demo result is not ready")
    return result


@router.post("/demo/jobs/{job_id}/cancel", response_model=MissionDemoJobResponse)
def cancel_demo_job(
    job_id: str,
    active_runner: DemoRunnerDependency,
) -> dict[str, object]:
    job = active_runner.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="demo job not found")
    return _public_demo_job(job)
