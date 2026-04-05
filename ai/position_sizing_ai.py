from typing import Dict, Any
from config.settings import settings

class PositionSizingAI:
    def adjust(self, position: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
        pnl = float(position.get("pnl_ratio", 0.0))
        confidence = float(features.get("confidence", 0.5))
        action = "hold"
        size_multiplier = 1.0
        if pnl > 0.01 and confidence > 0.7:
            action = "add_position"
            size_multiplier = min(1.5, settings.max_add_position_multiplier)
        if pnl < 0.005 and confidence < 0.5:
            action = "reduce_position"
            size_multiplier = 0.5
        if pnl < -settings.hard_stop_loss_pct:
            action = "stop_loss"
            size_multiplier = 0.0
        return {"action": action, "size_multiplier": size_multiplier}
