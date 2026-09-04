from __future__ import annotations

import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, RLock
from uuid import uuid4

from services.api.app.schemas.rapid_design import MissionDemoProfile
from services.api.app.services.rapid_design.config_loader import (
    load_mission_demo_profile,
    mission_demo_profile_hash,
)
from services.api.app.services.rapid_design.families.registry import FamilyRegistry, registry
from services.api.app.services.rapid_design.job_runner import TERMINAL_STATUSES
from services.api.app.services.rapid_design.mission_demo import (
    search_mission_demo,
    validate_mission_demo_submission,
)

DemoSearch = Callable[..., dict[str, object]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MissionDemoResultStore:
    """Persistence isolated from both formal state and the legacy jobs directory."""

    def __init__(
        self,
        root: Path | str = Path("storage") / "rapid_design" / "demo_jobs",
    ):
        self.root = Path(root)

    def job_dir(self, job_id: str) -> Path:
        if not job_id or any(part in job_id for part in ("/", "\\", "..")):
            raise ValueError("invalid demo job id")
        return self.root / job_id

    def write_json(self, job_id: str, name: str, payload: dict[str, object]) -> Path:
        target_dir = self.job_dir(job_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return target

    def read_result(self, job_id: str) -> dict[str, object] | None:
        path = self.job_dir(job_id) / "result.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class MissionDemoJobRunner:
    def __init__(
        self,
        *,
        profile: MissionDemoProfile | None = None,
        store: MissionDemoResultStore | None = None,
        family_registry: FamilyRegistry = registry,
        search: DemoSearch = search_mission_demo,
        max_workers: int = 1,
    ):
        self.profile = profile or load_mission_demo_profile()
        self.store = store or MissionDemoResultStore()
        self.family_registry = family_registry
        self._search = search
        self._jobs: dict[str, dict[str, object]] = {}
        self._events: dict[str, list[dict[str, object]]] = {}
        self._cancellations: dict[str, Event] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="mission-demo",
        )

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def create(
        self,
        *,
        family_id: str,
        preset_id: str,
        supplied_inputs: dict[str, float],
    ) -> dict[str, object]:
        inputs = validate_mission_demo_submission(
            profile=self.profile,
            family_id=family_id,
            preset_id=preset_id,
            supplied_inputs=supplied_inputs,
            family_registry=self.family_registry,
        )
        job_id = uuid4().hex
        timestamp = _now()
        job: dict[str, object] = {
            "id": job_id,
            "status": "queued",
            "progress": 0.0,
            "stage": "queued",
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "mode": "demo",
            "family_id": family_id,
            "preset_id": preset_id,
            "profile_id": self.profile.profile_id,
            "profile_version": self.profile.profile_version,
            "formal_status": self.profile.formal_status,
            "inputs": inputs,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._events[job_id] = []
            self._cancellations[job_id] = Event()
            self._publish_locked(job_id, "queued", "Demo search queued")
        self.store.write_json(
            job_id,
            "request.json",
            {
                "mode": "demo",
                "family_id": family_id,
                "preset_id": preset_id,
                "inputs": inputs,
            },
        )
        self.store.write_json(
            job_id,
            "profile.json",
            {
                **self.profile.model_dump(mode="json"),
                "profile_hash": mission_demo_profile_hash(self.profile),
            },
        )
        self.store.write_json(job_id, "status.json", dict(job))
        self._executor.submit(self._run, job_id)
        return self.get(job_id) or {}

    def get(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def events_since(self, job_id: str, offset: int) -> list[dict[str, object]]:
        with self._lock:
            return deepcopy(self._events.get(job_id, [])[offset:])

    def cancel(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if str(job["status"]) not in TERMINAL_STATUSES:
                self._cancellations[job_id].set()
                job["stage"] = "cancelling"
                job["updated_at"] = _now()
                self._publish_locked(job_id, "progress", "Stopping demo search")
                self.store.write_json(job_id, "status.json", dict(job))
            return deepcopy(job)

    def result(self, job_id: str) -> dict[str, object] | None:
        return self.store.read_result(job_id)

    def _publish_locked(self, job_id: str, event_type: str, message: str) -> None:
        job = self._jobs[job_id]
        event = {
            "sequence": len(self._events[job_id]),
            "type": event_type,
            "job_id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "stage": job["stage"],
            "message": message,
            "timestamp": _now(),
            "mode": "demo",
            "family_id": job["family_id"],
            "preset_id": job["preset_id"],
            "profile_id": job["profile_id"],
            "profile_version": job["profile_version"],
            "formal_status": job["formal_status"],
        }
        self._events[job_id].append(event)

    def _set_state(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        stage: str | None = None,
        error: str | None = None,
        event_type: str = "progress",
        message: str,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if status is not None:
                job["status"] = status
            if progress is not None:
                job["progress"] = max(0.0, min(1.0, progress))
            if stage is not None:
                job["stage"] = stage
            job["error"] = error
            job["updated_at"] = _now()
            self._publish_locked(job_id, event_type, message)
            self.store.write_json(job_id, "status.json", dict(job))

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        cancellation = self._cancellations[job_id]
        if cancellation.is_set():
            self._set_state(
                job_id,
                status="cancelled",
                stage="cancelled",
                event_type="cancelled",
                message="Demo search cancelled",
            )
            return
        self._set_state(
            job_id,
            status="running",
            progress=0.02,
            stage="evaluating",
            message="Evaluating native conventional geometry candidates",
        )

        def on_progress(
            completed: int,
            total: int,
            record: dict[str, object],
        ) -> None:
            validity = "valid" if record["valid"] else "invalid"
            self._set_state(
                job_id,
                progress=0.02 + 0.94 * completed / total,
                stage="evaluating",
                message=f"Demo evaluation {completed}/{total} ({validity})",
            )

        try:
            result = self._search(
                job_id=job_id,
                family_id=str(job["family_id"]),
                preset_id=str(job["preset_id"]),
                inputs=dict(job["inputs"]),
                profile=self.profile,
                on_progress=on_progress,
                is_cancelled=cancellation.is_set,
                family_registry=self.family_registry,
            )
            self.store.write_json(job_id, "result.json", result)
            self._set_state(
                job_id,
                status="succeeded",
                progress=1.0,
                stage="completed",
                event_type="completed",
                message="Demo candidates generated",
            )
        except InterruptedError:
            self._set_state(
                job_id,
                status="cancelled",
                stage="cancelled",
                event_type="cancelled",
                message="Demo search cancelled",
            )
        except Exception as exc:  # noqa: BLE001 - background jobs persist all failures
            self._set_state(
                job_id,
                status="failed",
                stage="failed",
                error=str(exc),
                event_type="failed",
                message="Demo search failed",
            )
