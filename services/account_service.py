from typing import Dict, Any
from clients.okx_client import OKXClient
from config.settings import settings

class AccountService:
    def __init__(self) -> None:
        self.client = OKXClient()

    def credentials_ready(self) -> bool:
        return all([settings.okx_api_key, settings.okx_api_secret, settings.okx_api_passphrase])

    def get_account_summary(self) -> Dict[str, float]:
        payload = self.client.safe_get_balance()
        rows = payload.get("data", [])
        if not rows:
            return {"equity": 0.0, "available": 0.0, "used_margin": 0.0}
        row = rows[0]
        try:
            equity = float(row.get("totalEq", 0.0))
            available = float(row.get("adjEq", 0.0))
        except (TypeError, ValueError):
            equity, available = 0.0, 0.0
        return {"equity": equity, "available": available, "used_margin": max(equity - available, 0.0)}
