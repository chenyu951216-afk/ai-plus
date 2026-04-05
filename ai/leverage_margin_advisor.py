from typing import Dict, Any
from config.settings import settings

class LeverageMarginAdvisor:
    def suggest(self, confidence: float, features: Dict[str, Any]) -> Dict[str, Any]:
        atr_ratio = float(features.get("atr_ratio", 0.0))
        leverage = settings.default_leverage_min + int((settings.default_leverage_max - settings.default_leverage_min) * confidence)
        if atr_ratio > 0.03:
            leverage = max(settings.default_leverage_min, leverage - 4)
        margin_pct = settings.default_margin_pct_min + (settings.default_margin_pct_max - settings.default_margin_pct_min) * confidence
        return {"suggested_leverage": int(max(settings.default_leverage_min, min(leverage, settings.default_leverage_max))), "suggested_margin_pct": round(max(settings.default_margin_pct_min, min(margin_pct, settings.default_margin_pct_max)), 4), "preferred_order_type": "limit" if confidence < 0.85 else "post_only"}
