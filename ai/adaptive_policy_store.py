import json
from pathlib import Path
from typing import Any, Dict

from config.settings import settings


class AdaptivePolicyStore:
    def __init__(self) -> None:
        base = Path(settings.state_dir)
        base.mkdir(parents=True, exist_ok=True)
        self.file_path = base / "adaptive_policy.json"
        self.defaults = {
            "entry_confidence_shift": 0.0,
            "size_multiplier_bias": 1.0,
            "leverage_bias": 1.0,
            "breakout_bias": 0.0,
            "trend_follow_bias": 0.0,
            "preferred_style": "balanced",
            "entry_aggression": 0.0,
            "breakout_tolerance": 0.0,
            "pullback_preference": 0.0,
            "protection_profile": "balanced",
            "exit_style": "balanced",
            "position_management_profile": "balanced",
            "initial_stop_loss_atr": settings.initial_stop_loss_atr,
            "initial_take_profit_atr": settings.initial_take_profit_atr,
            "break_even_trigger_rr": settings.break_even_trigger_rr,
            "trailing_activation_rr": settings.trailing_activation_rr,
            "trailing_buffer_atr": settings.trailing_buffer_atr,
            "scale_in_aggression": 0.0,
            "scale_out_aggression": 0.0,
            "partial_take_profit_rr": settings.lifecycle_partial_take_profit_rr,
            "reentry_after_partial": 0.0,
            "protection_refresh_bias": 0.0,
            "break_even_lock_ratio": settings.lifecycle_break_even_lock_ratio,
            "trailing_step_rr": settings.lifecycle_trailing_step_rr,
            "tp1_fraction": settings.lifecycle_tp1_fraction,
            "tp2_fraction": settings.lifecycle_tp2_fraction,
            "protection_refresh_cooldown_sec": settings.lifecycle_protection_refresh_cooldown_sec,
            "last_reflection": "",
            "last_review_day": "",
            "last_review_summary": "",
            "last_review_consensus": {},
            "gpt_enabled": bool(settings.enable_gpt_reflection and settings.openai_api_key),
        }

    def load(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            return dict(self.defaults)
        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
            merged = dict(self.defaults)
            if isinstance(payload, dict):
                merged.update(payload)
            return merged
        except Exception:
            return dict(self.defaults)

    def save(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(self.defaults)
        merged.update(payload or {})
        self.file_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged
