import json
import os
from pathlib import Path


class RapidDesignResultStore:
    def __init__(self, root: Path | str = Path("storage") / "rapid_design"):
        self.root = Path(root)

    def job_dir(self, job_id: str) -> Path:
        if not job_id or any(part in job_id for part in ("/", "\\", "..")):
            raise ValueError("invalid job id")
        return self.root / "jobs" / job_id

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
