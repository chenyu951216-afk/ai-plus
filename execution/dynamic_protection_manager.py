from typing import Dict, Any
from config.settings import settings

class DynamicProtectionManager:
    def manage(self, position: Dict[str, Any], atr: float) -> Dict[str, Any]:
        entry = float(position.get("entry_price", 0.0))
        current = float(position.get("current_price", 0.0))
        side = str(position.get("side", "long"))
        sl = float(position.get("stop_loss_price", 0.0))
        if entry <= 0 or current <= 0:
            return {"action": "invalid"}

        if side == "short":
            reward = max(entry - current, 0.0)
            risk = max(sl - entry, 1e-9)
            pnl = (entry - current) / entry
        else:
            reward = max(current - entry, 0.0)
            risk = max(entry - sl, 1e-9)
            pnl = (current - entry) / entry

        rr = reward / risk
        action = "hold"
        new_sl = sl
        if pnl <= -settings.hard_stop_loss_pct:
            action = "force_exit"
        elif rr >= settings.trailing_activation_rr and atr > 0:
            action = "trailing_active"
            new_sl = current + atr * settings.trailing_buffer_atr if side == "short" else current - atr * settings.trailing_buffer_atr
        elif rr >= settings.break_even_trigger_rr:
            action = "move_to_break_even"
            new_sl = entry
        elif pnl >= settings.min_lock_profit_pct:
            action = "soft_profit_protect"
        return {"action": action, "new_stop_loss_price": round(new_sl, 8), "pnl_ratio": round(pnl, 6), "rr_progress": round(rr, 4)}
