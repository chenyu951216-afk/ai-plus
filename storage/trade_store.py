import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from config.settings import settings


class TradeStore:
    def __init__(self) -> None:
        p = Path(settings.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        self.file_path = p / "trade_records.jsonl"

    def append(self, record: Dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _all(self) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        return [json.loads(x) for x in self.file_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._all()[-limit:]

    def records_for_day(self, day: str, tz_name: str | None = None) -> List[Dict[str, Any]]:
        tz = ZoneInfo(tz_name or settings.gpt_review_timezone)
        out: List[Dict[str, Any]] = []
        for row in self._all():
            ts = str(row.get("timestamp", ""))
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone(tz).date().isoformat() == day:
                out.append(row)
        return out

    def latest_trading_day(self, tz_name: str | None = None) -> str:
        tz = ZoneInfo(tz_name or settings.gpt_review_timezone)
        rows = self._all()
        if not rows:
            return ""
        for row in reversed(rows):
            ts = str(row.get("timestamp", ""))
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(tz).date().isoformat()
            except Exception:
                continue
        return ""

    def consecutive_losses(self, limit: int = 50) -> int:
        streak = 0
        for row in reversed(self.recent(limit=limit)):
            if float(row.get("pnl", 0.0) or 0.0) > 0:
                break
            streak += 1
        return streak

    def summary(self, limit: int = 50) -> Dict[str, Any]:
        rows = self.recent(limit=limit)
        if not rows:
            return {"count": 0, "wins": 0, "losses": 0, "avg_pnl": 0.0, "consecutive_losses": 0}
        wins = sum(1 for row in rows if float(row.get("pnl", 0.0) or 0.0) > 0)
        losses = len(rows) - wins
        avg_pnl = sum(float(row.get("pnl", 0.0) or 0.0) for row in rows) / len(rows)
        return {
            "count": len(rows),
            "wins": wins,
            "losses": losses,
            "avg_pnl": round(avg_pnl, 6),
            "consecutive_losses": self.consecutive_losses(limit=limit),
        }
