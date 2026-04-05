import json
import time
from pathlib import Path
from typing import Any, Dict

from config.settings import settings


class PositionLifecycleStore:
    def __init__(self) -> None:
        p = Path(settings.state_dir)
        p.mkdir(parents=True, exist_ok=True)
        self.file_path = p / "position_lifecycle_state.json"

    def _load_all(self) -> Dict[str, Dict[str, Any]]:
        if not self.file_path.exists():
            return {}
        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _save_all(self, payload: Dict[str, Dict[str, Any]]) -> None:
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _key(self, symbol: str, side: str) -> str:
        return f"{symbol}:{side or 'net'}"

    def get(self, symbol: str, side: str) -> Dict[str, Any]:
        rows = self._load_all()
        key = self._key(symbol, side)
        default = {
            "scale_in_count": 0,
            "partial_exit_count": 0,
            "tp1_done": False,
            "tp2_done": False,
            "last_refresh_ts": 0.0,
            "last_action": "none",
            "last_reason": "",
            "last_update_ts": 0.0,
        }
        row = rows.get(key, {})
        if not isinstance(row, dict):
            row = {}
        out = dict(default)
        out.update(row)
        return out

    def update(self, symbol: str, side: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        rows = self._load_all()
        key = self._key(symbol, side)
        current = self.get(symbol, side)
        current.update(updates or {})
        current["last_update_ts"] = time.time()
        rows[key] = current
        self._save_all(rows)
        return current

    def mark_refresh(self, symbol: str, side: str, reason: str) -> Dict[str, Any]:
        return self.update(symbol, side, {"last_refresh_ts": time.time(), "last_action": "refresh_protection", "last_reason": reason})

    def clear(self, symbol: str, side: str) -> None:
        rows = self._load_all()
        rows.pop(self._key(symbol, side), None)
        self._save_all(rows)
