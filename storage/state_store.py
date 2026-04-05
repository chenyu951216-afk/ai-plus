import json
from pathlib import Path
from typing import Dict, Any
from config.settings import settings

class StateStore:
    def __init__(self) -> None:
        p = Path(settings.state_dir); p.mkdir(parents=True, exist_ok=True)
        self.file_path = p / "dashboard_state.json"
    def save(self, payload: Dict[str, Any]) -> None:
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    def load(self) -> Dict[str, Any]:
        if not self.file_path.exists(): return {}
        return json.loads(self.file_path.read_text(encoding="utf-8"))
