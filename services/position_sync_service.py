from typing import Dict, Any, List
from clients.okx_client import OKXClient
from config.settings import settings

class PositionSyncService:
    def __init__(self) -> None:
        self.client = OKXClient()

    def sync(self) -> List[Dict[str, Any]]:
        if not settings.enable_position_sync:
            return []
        payload = self.client.safe_get_positions()
        out = []
        for row in payload.get("data", []):
            try:
                out.append({
                    "symbol": row.get("instId", ""),
                    "side": row.get("posSide", ""),
                    "size": float(row.get("pos", 0.0)),
                    "entry_price": float(row.get("avgPx", 0.0)),
                    "current_price": float(row.get("markPx", row.get("avgPx", 0.0))),
                    "upl": float(row.get("upl", 0.0)),
                    "upl_ratio": float(row.get("uplRatio", 0.0)),
                })
            except (TypeError, ValueError):
                continue
        return out
