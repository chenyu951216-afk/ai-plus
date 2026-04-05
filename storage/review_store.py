import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from config.settings import settings


class ReviewStore:
    def __init__(self) -> None:
        p = Path(settings.state_dir)
        p.mkdir(parents=True, exist_ok=True)
        self.file_path = p / "daily_gpt_reviews.jsonl"

    def append(self, record: Dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        rows = [json.loads(x) for x in self.file_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        return rows[-limit:]

    def last(self) -> Dict[str, Any]:
        rows = self.recent(limit=1)
        return rows[-1] if rows else {}
