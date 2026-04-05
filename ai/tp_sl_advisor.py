from typing import Dict, Any
from config.settings import settings

class TPSLAdvisor:
    def suggest(self, features: Dict[str, Any], side: str, confidence: float) -> Dict[str, Any]:
        last_price = float(features.get("last_price", 0.0))
        atr = float(features.get("atr", 0.0))
        if last_price <= 0 or atr <= 0:
            return {"entry_hint": last_price, "stop_loss_price": 0.0, "take_profit_price": 0.0}
        sl_atr = settings.initial_stop_loss_atr
        tp_atr = settings.initial_take_profit_atr + (0.4 if confidence >= 0.75 else 0.0)
        if side == "short":
            return {"entry_hint": last_price, "stop_loss_price": round(last_price + atr * sl_atr, 8), "take_profit_price": round(last_price - atr * tp_atr, 8)}
        return {"entry_hint": last_price, "stop_loss_price": round(last_price - atr * sl_atr, 8), "take_profit_price": round(last_price + atr * tp_atr, 8)}
