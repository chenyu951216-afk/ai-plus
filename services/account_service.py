from typing import Dict, Any
import time

from clients.okx_client import OKXClient
from config.settings import settings


class AccountService:
    def __init__(self) -> None:
        self.client = OKXClient()

    def credentials_ready(self) -> bool:
        return all([settings.okx_api_key, settings.okx_api_secret, settings.okx_api_passphrase])

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    def get_account_summary(self) -> Dict[str, float]:
        payload = self.client.safe_get_balance()
        rows = payload.get("data", [])

        if not rows:
            return {"equity": 0.0, "available": 0.0, "used_margin": 0.0}

        row = rows[0]
        details = row.get("details", []) or []

        usdt_detail = None
        for d in details:
            if str(d.get("ccy", "")).upper() == "USDT":
                usdt_detail = d
                break

        if usdt_detail:
            equity = self._to_float(usdt_detail.get("eq"))
            available = self._to_float(usdt_detail.get("availBal"))
        else:
            equity = self._to_float(row.get("totalEq"))
            available = self._to_float(row.get("adjEq"))

        return {
            "equity": equity,
            "available": available,
            "used_margin": max(equity - available, 0.0),
        }

    def summary(self) -> Dict[str, Any]:
        account = self.get_account_summary()
        return {
            "equity": float(account.get("equity", 0.0)),
            "available": float(account.get("available", 0.0)),
            "available_equity": float(account.get("available", 0.0)),
            "used_margin": float(account.get("used_margin", 0.0)),
            "timestamp": int(time.time()),
            "credentials_ready": self.credentials_ready(),
            "pos_mode": "net",
        }
