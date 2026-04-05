import json
from pathlib import Path
from typing import Dict, Any, List
from config.settings import settings

class ProtectiveOrderStore:
    def __init__(self) -> None:
        p = Path(settings.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        self.file_path = p / "protective_order_records.jsonl"

    def append(self, record: Dict[str, Any]) -> None:
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        return [json.loads(x) for x in self.file_path.read_text(encoding="utf-8").splitlines()[-limit:] if x.strip()]

    def latest_for_symbol(self, symbol: str) -> Dict[str, Any]:
        for row in reversed(self.recent(limit=400)):
            if str(row.get("symbol", "")) == symbol:
                return row
        return {}
