import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from services.api.app.schemas.rapid_design import (
    RapidAnalyzeRequest,
    RapidAnalyzeResponse,
    RapidDesignJobResponse,
    RapidDesignRequest,
)
from services.api.app.services.rapid_design.bwb_analysis import analyze_bwb
from services.api.app.services.rapid_design.config_loader import load_rapid_design_config
from services.api.app.services.rapid_design.job_runner import (
    TERMINAL_STATUSES,
    RapidDesignJobRunner,
)

router = APIRouter(prefix="/api/rapid-design", tags=["rapid-design"])
runner = RapidDesignJobRunner()


def _public_job(job: dict[str, object]) -> dict[str, object]:
    return {key: job[key] for key in RapidDesignJobResponse.model_fields}


@router.get("/config")
def get_config():
    return load_rapid_design_config().model_dump(mode="json")


@router.post("/analyze", response_model=RapidAnalyzeResponse)
def analyze(request: RapidAnalyzeRequest) -> RapidAnalyzeResponse:
    return analyze_bwb(request)


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
