"""Small public entry point for Design and Analyze, with anonymous browser sessions."""

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from secrets import token_urlsafe
from threading import RLock

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response

from services.api.app.routers.rapid_design import get_demo_runner, router
from services.api.app.services.rapid_design.mission_demo_job_runner import (
    DEMO_TERMINAL_STATUSES,
    MissionDemoJobRunner,
    MissionDemoResultStore,
)

COOKIE_NAME = "rapid_demo_visitor"
VISITOR_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


class VisitorDemoRunner:
    """Use the existing search engine while restricting job access to one browser."""

    def __init__(self, runner: MissionDemoJobRunner, visitor: str | None, lock: RLock):
        self.runner = runner
        self.visitor = visitor
        self.lock = lock

    def _owns(self, job_id: str) -> bool:
        if not self.visitor:
            return False
        try:
            owner = self.runner.store.job_dir(job_id) / "visitor.txt"
            return owner.read_text(encoding="utf-8") == self.visitor
        except (OSError, ValueError):
            return False

    def create(self, **kwargs) -> dict[str, object]:
        with self.lock:
            jobs = self.runner.list_recent(limit=1_000_000)
            active = [job for job in jobs if job["status"] not in DEMO_TERMINAL_STATUSES]
            if any(self._owns(str(job["id"])) for job in active):
                raise HTTPException(429, "Your previous run is still processing. Please wait.")
            if len(active) >= 4:
                raise HTTPException(503, "The demo is busy. Please try again in a moment.")
            job = self.runner.create(**kwargs)
            owner = self.runner.store.job_dir(str(job["id"])) / "visitor.txt"
            owner.write_text(str(self.visitor), encoding="utf-8")
            return job

    def get(self, job_id: str) -> dict[str, object] | None:
        return self.runner.get(job_id) if self._owns(job_id) else None

    def list_recent(self, *, limit: int = 10) -> list[dict[str, object]]:
        if not self.visitor:
            return []
        return [
            job for job in self.runner.list_recent(limit=1_000_000)
            if self._owns(str(job["id"]))
        ][:limit]

    def events_since(self, job_id: str, offset: int) -> list[dict[str, object]]:
        return self.runner.events_since(job_id, offset) if self._owns(job_id) else []

    def result(self, job_id: str) -> dict[str, object] | None:
        return self.runner.result(job_id) if self._owns(job_id) else None

    def cancel(self, job_id: str) -> dict[str, object] | None:
        return self.runner.cancel(job_id) if self._owns(job_id) else None


def create_app(storage_root: Path | None = None) -> FastAPI:
    root = storage_root or Path(os.getenv("RAPID_DEMO_STORAGE", "storage/public_demo"))
    active_runner = MissionDemoJobRunner(store=MissionDemoResultStore(root / "jobs"))
    creation_lock = RLock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        active_runner.shutdown()

    app = FastAPI(title="Rapid Process Design Demo", lifespan=lifespan)
    app.state.demo_runner = active_runner

    def visitor_runner(request: Request, response: Response) -> VisitorDemoRunner:
        visitor = request.cookies.get(COOKIE_NAME)
        if visitor is not None and not VISITOR_PATTERN.fullmatch(visitor):
            visitor = None
        # Read-only requests never mint competing cookies during initial page loading.
        if visitor is None and request.method == "POST" and request.url.path.endswith("/jobs"):
            visitor = token_urlsafe(32)
            response.set_cookie(
                COOKIE_NAME,
                visitor,
                max_age=60 * 60 * 24 * 7,
                httponly=True,
                secure=os.getenv("RAPID_SECURE_COOKIES", "true").lower() == "true",
                samesite="lax",
                path="/",
            )
        return VisitorDemoRunner(active_runner, visitor, creation_lock)

    app.dependency_overrides[get_demo_runner] = visitor_runner
    public_routes = APIRouter()
    prefix = "/api/rapid-design"
    for route in router.routes:
        path = getattr(route, "path", "")
        if (
            path in {f"{prefix}/families", f"{prefix}/analyze"}
            or path.startswith((f"{prefix}/families/", f"{prefix}/demo/"))
        ):
            public_routes.routes.append(route)
    app.include_router(public_routes)

    @app.middleware("http")
    async def uncached_api(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "rapid-process-design-demo"}

    return app
