from typing import Dict, Any
from config.settings import settings

class RiskGuardAI:
    def evaluate(self, account: Dict[str, Any]) -> Dict[str, Any]:
        equity = float(account.get("equity", 0.0))
        used_margin = float(account.get("used_margin", 0.0))
        current_risk = 0.0 if equity <= 0 else used_margin / equity
        blocked = current_risk >= settings.max_total_risk_pct
        return {"blocked": blocked, "current_risk_pct": round(current_risk, 6), "reason": "max_total_risk_exceeded" if blocked else "risk_ok"}
