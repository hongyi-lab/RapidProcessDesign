from __future__ import annotations

import json
import os
import re
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
DEMO_TERMINAL_STATUSES = {*TERMINAL_STATUSES, "interrupted"}

_JOB_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_PERSISTED_FILE_NAMES = {
    "request.json",
    "profile.json",
    "status.json",
    "result.json",
}


class MissionDemoPersistenceError(RuntimeError):
    """A persisted Demo artifact is missing, malformed, or belongs elsewhere."""


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
        if not _JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("invalid demo job id")
        root = self.root.resolve()
        target = (root / job_id).resolve()
        if target.parent != root:
            raise ValueError("invalid demo job id")
        return target

    @staticmethod
    def _validate_name(name: str) -> None:
        if name not in _PERSISTED_FILE_NAMES:
            raise ValueError("invalid demo artifact name")

    def write_json(self, job_id: str, name: str, payload: dict[str, object]) -> Path:
        self._validate_name(name)
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

    def read_json(self, job_id: str, name: str) -> dict[str, object] | None:
        self._validate_name(name)
        path = self.job_dir(job_id) / name
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MissionDemoPersistenceError(
                f"could not read persisted Demo artifact {name}"
            ) from exc
        if not isinstance(payload, dict):
            raise MissionDemoPersistenceError(
                f"persisted Demo artifact {name} is not an object"
            )
        return payload

    def read_result(self, job_id: str) -> dict[str, object] | None:
        return self.read_json(job_id, "result.json")

    def job_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        job_ids: list[str] = []
        for entry in self.root.iterdir():
            if entry.is_symlink() or not entry.is_dir():
                continue
            try:
                self.job_dir(entry.name)
            except ValueError:
                continue
            job_ids.append(entry.name)
        return sorted(job_ids)


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
        self._restore_persisted_jobs()
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
            if job_id not in self._jobs:
                try:
                    self._restore_job_locked(job_id)
                except (MissionDemoPersistenceError, ValueError):
                    return None
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def list_recent(self, *, limit: int = 10) -> list[dict[str, object]]:
        if limit < 1:
            return []
        with self._lock:
            for job_id in self.store.job_ids():
                if job_id not in self._jobs:
                    try:
                        self._restore_job_locked(job_id)
                    except (MissionDemoPersistenceError, ValueError):
                        continue
            jobs = sorted(
                self._jobs.values(),
                key=lambda job: (
                    str(job.get("updated_at", "")),
                    str(job.get("created_at", "")),
                    str(job.get("id", "")),
                ),
                reverse=True,
            )
            return deepcopy(jobs[:limit])

    def events_since(self, job_id: str, offset: int) -> list[dict[str, object]]:
        self.get(job_id)
        with self._lock:
            return deepcopy(self._events.get(job_id, [])[max(0, offset) :])

    def cancel(self, job_id: str) -> dict[str, object] | None:
        self.get(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if str(job["status"]) not in DEMO_TERMINAL_STATUSES:
                self._cancellations[job_id].set()
                job["stage"] = "cancelling"
                job["updated_at"] = _now()
                self._publish_locked(job_id, "progress", "Stopping demo search")
                self.store.write_json(job_id, "status.json", dict(job))
            return deepcopy(job)

    def result(self, job_id: str) -> dict[str, object] | None:
        job = self.get(job_id)
        if job is None:
            return None
        result = self.store.read_result(job_id)
        if result is None:
            if job["status"] == "succeeded":
                raise MissionDemoPersistenceError(
                    "persisted Demo job is marked succeeded but has no result"
                )
            return None
        profile = self.store.read_json(job_id, "profile.json")
        self._validate_result_ownership(job_id, job, result, profile)
        return result

    def _restore_persisted_jobs(self) -> None:
        with self._lock:
            for job_id in self.store.job_ids():
                try:
                    self._restore_job_locked(job_id)
                except (MissionDemoPersistenceError, ValueError):
                    # A malformed directory is not exposed as somebody else's job.
                    continue

    def _restore_job_locked(self, job_id: str) -> None:
        if job_id in self._jobs:
            return
        status = self.store.read_json(job_id, "status.json")
        if status is None:
            return
        request = self.store.read_json(job_id, "request.json")
        profile = self.store.read_json(job_id, "profile.json")
        self._validate_persisted_bundle(job_id, status, request, profile)

        job = dict(status)
        self._jobs[job_id] = job
        self._events[job_id] = []
        self._cancellations[job_id] = Event()

        try:
            result = self.store.read_result(job_id)
            if result is not None:
                self._validate_result_ownership(job_id, job, result, profile)
        except MissionDemoPersistenceError as exc:
            self._mark_recovery_failure_locked(job_id, str(exc))
            return

        previous_status = str(job["status"])
        if result is not None:
            expected_stage = self._result_stage(result)
            if (
                previous_status != "succeeded"
                or float(job.get("progress", 0.0)) != 1.0
                or str(job.get("stage")) != expected_stage
            ):
                job["status"] = "succeeded"
                job["progress"] = 1.0
                job["stage"] = expected_stage
                job["error"] = None
                job["updated_at"] = _now()
                self.store.write_json(job_id, "status.json", dict(job))
            self._publish_locked(
                job_id,
                "recovered",
                "Completed Demo result recovered from persisted artifacts",
            )
            return

        if previous_status in {"queued", "running"} or str(job["stage"]) == "cancelling":
            job["status"] = "interrupted"
            job["stage"] = "interrupted"
            job["error"] = (
                "Demo search was interrupted by a service restart; automatic resume "
                "is not supported."
            )
            job["updated_at"] = _now()
            self.store.write_json(job_id, "status.json", dict(job))
            self._publish_locked(job_id, "interrupted", str(job["error"]))
            return

        if previous_status == "succeeded":
            self._mark_recovery_failure_locked(
                job_id,
                "persisted Demo job is marked succeeded but has no result",
            )
            return

        if previous_status not in DEMO_TERMINAL_STATUSES:
            self._mark_recovery_failure_locked(
                job_id,
                f"persisted Demo job has unknown status: {previous_status}",
            )
            return

        self._publish_locked(
            job_id,
            "recovered",
            f"Terminal Demo job recovered with status {previous_status}",
        )

    @staticmethod
    def _validate_persisted_bundle(
        job_id: str,
        status: dict[str, object],
        request: dict[str, object] | None,
        profile: dict[str, object] | None,
    ) -> None:
        required = {
            "id",
            "status",
            "progress",
            "stage",
            "error",
            "created_at",
            "updated_at",
            "mode",
            "family_id",
            "preset_id",
            "profile_id",
            "profile_version",
            "formal_status",
            "inputs",
        }
        if required - status.keys():
            raise MissionDemoPersistenceError(
                "persisted Demo status is missing required fields"
            )
        if status["id"] != job_id or status["mode"] != "demo":
            raise MissionDemoPersistenceError(
                "persisted Demo status does not belong to the requested job"
            )
        if request is None or profile is None:
            raise MissionDemoPersistenceError(
                "persisted Demo request or profile artifact is missing"
            )
        expected_request = {
            "mode": status["mode"],
            "family_id": status["family_id"],
            "preset_id": status["preset_id"],
            "inputs": status["inputs"],
        }
        if any(request.get(key) != value for key, value in expected_request.items()):
            raise MissionDemoPersistenceError(
                "persisted Demo request does not match its status"
            )
        expected_profile = {
            "profile_id": status["profile_id"],
            "profile_version": status["profile_version"],
            "formal_status": status["formal_status"],
        }
        if any(profile.get(key) != value for key, value in expected_profile.items()):
            raise MissionDemoPersistenceError(
                "persisted Demo profile does not match its status"
            )

    @staticmethod
    def _validate_result_ownership(
        job_id: str,
        job: dict[str, object],
        result: dict[str, object],
        persisted_profile: dict[str, object] | None,
    ) -> None:
        if result.get("job_id") != job_id:
            raise MissionDemoPersistenceError(
                "persisted Demo result belongs to a different job"
            )
        for key in (
            "mode",
            "formal_status",
            "family_id",
            "preset_id",
            "inputs",
        ):
            if result.get(key) != job.get(key):
                raise MissionDemoPersistenceError(
                    f"persisted Demo result {key} does not match its request"
                )
        result_profile = result.get("profile")
        if not isinstance(result_profile, dict):
            raise MissionDemoPersistenceError(
                "persisted Demo result has no profile provenance"
            )
        if (
            result_profile.get("id") != job.get("profile_id")
            or result_profile.get("version") != job.get("profile_version")
        ):
            raise MissionDemoPersistenceError(
                "persisted Demo result profile does not match its request"
            )
        if persisted_profile is None:
            raise MissionDemoPersistenceError(
                "persisted Demo result has no matching profile artifact"
            )
        persisted_hash = persisted_profile.get("profile_hash")
        if not isinstance(persisted_hash, str) or not persisted_hash:
            raise MissionDemoPersistenceError(
                "persisted Demo profile has no provenance hash"
            )
        if result_profile.get("hash") != persisted_hash:
            raise MissionDemoPersistenceError(
                "persisted Demo result profile hash does not match its request"
            )

    @staticmethod
    def _result_stage(result: dict[str, object]) -> str:
        outcome = str(result.get("status", ""))
        if outcome in {"no_valid_candidates", "no_valid_evaluations"}:
            return "no_valid_candidates"
        if outcome in {
            "no_feasible_solution_found",
            "no_feasible_candidates",
        }:
            return "no_feasible_candidates"
        return "completed"

    def _mark_recovery_failure_locked(self, job_id: str, error: str) -> None:
        job = self._jobs[job_id]
        job["status"] = "failed"
        job["stage"] = "recovery_error"
        job["error"] = f"Persisted Demo recovery failed: {error}"
        job["updated_at"] = _now()
        self.store.write_json(job_id, "status.json", dict(job))
        self._publish_locked(job_id, "failed", str(job["error"]))

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
            stage = self._result_stage(result)
            if stage == "no_valid_candidates":
                message = "Demo search completed without a valid candidate"
            elif stage == "no_feasible_candidates":
                message = (
                    "Demo search completed; candidates do not satisfy the connected "
                    "Demo constraints"
                )
            else:
                message = "Demo candidates generated"
            self._set_state(
                job_id,
                status="succeeded",
                progress=1.0,
                stage=stage,
                event_type="completed",
                message=message,
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
                stage="program_error",
                error=str(exc),
                event_type="failed",
                message="Demo search failed",
            )
