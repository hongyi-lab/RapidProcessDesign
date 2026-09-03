from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from threading import Event, RLock
from uuid import uuid4

from services.api.app.schemas.rapid_design import RapidDesignConfig
from services.api.app.services.rapid_design.config_loader import (
    load_rapid_design_config,
    validated_inputs,
)
from services.api.app.services.rapid_design.optimizer import optimize_design
from services.api.app.services.rapid_design.result_store import RapidDesignResultStore

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RapidDesignJobRunner:
    def __init__(
        self,
        *,
        config: RapidDesignConfig | None = None,
        store: RapidDesignResultStore | None = None,
        max_workers: int = 1,
    ):
        self.config = config or load_rapid_design_config()
        self.store = store or RapidDesignResultStore()
        self._jobs: dict[str, dict[str, object]] = {}
        self._events: dict[str, list[dict[str, object]]] = {}
        self._cancellations: dict[str, Event] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="rapid-design"
        )

    def create(self, supplied_inputs: dict[str, float]) -> dict[str, object]:
        inputs = validated_inputs(self.config, supplied_inputs)
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
            "inputs": inputs,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._events[job_id] = []
            self._cancellations[job_id] = Event()
            self._publish_locked(job_id, "queued", "任务已进入队列")
        self.store.write_json(job_id, "request.json", {"inputs": inputs})
        self.store.write_json(
            job_id,
            "config.json",
            self.config.model_dump(mode="json"),
        )
        self._executor.submit(self._run, job_id)
        return self.get(job_id)

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
                self._publish_locked(job_id, "progress", "正在停止优化")
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
        inputs = dict(job["inputs"])
        cancellation = self._cancellations[job_id]
        self._set_state(
            job_id,
            status="running",
            progress=0.03,
            stage="initializing_surrogate",
            message="正在载入公开气动代理模型",
        )

        def on_progress(iteration: int, total: int, entry: dict[str, object]) -> None:
            feasible_label = "，已找到可行点" if entry["feasible"] else ""
            self._set_state(
                job_id,
                progress=0.08 + 0.86 * iteration / total,
                stage="optimizing",
                message=f"优化第 {iteration}/{total} 轮{feasible_label}",
            )

        try:
            result = optimize_design(
                job_id=job_id,
                inputs=inputs,
                config=self.config,
                on_progress=on_progress,
                is_cancelled=cancellation.is_set,
            )
            self.store.write_json(job_id, "result.json", result)
            self._set_state(
                job_id,
                status="succeeded",
                progress=1.0,
                stage="completed",
                event_type="completed",
                message="设计结果已生成",
            )
        except InterruptedError:
            self._set_state(
                job_id,
                status="cancelled",
                stage="cancelled",
                event_type="cancelled",
                message="优化已停止",
            )
        except Exception as exc:  # noqa: BLE001 - background jobs must persist all failures
            self._set_state(
                job_id,
                status="failed",
                stage="failed",
                error=str(exc),
                event_type="failed",
                message="设计生成失败",
            )
