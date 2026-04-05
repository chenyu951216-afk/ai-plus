import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from config.settings import settings

class ProjectMemoryBackup:
    def __init__(self) -> None:
        p = Path(settings.data_dir); p.mkdir(parents=True, exist_ok=True)
        self.log_file = p / "project_memory_log.jsonl"
        self.snapshot_file = p / "project_memory_latest.json"

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def add_record(self, step_title: str, change_reason: str, changed_files: List[str], detail: str, tags: List[str] | None = None) -> Dict[str, Any]:
        payload = {"time": self._now(), "step_title": step_title, "change_reason": change_reason, "changed_files": changed_files, "detail": detail, "tags": tags or []}
        with self.log_file.open("a", encoding="utf-8") as f: f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.snapshot_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
