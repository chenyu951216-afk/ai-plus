from __future__ import annotations

from typing import Any, Dict

from ai.adaptive_policy_store import AdaptivePolicyStore
from config.settings import settings


class OptimizationApplyService:
    def __init__(self) -> None:
        self.store = AdaptivePolicyStore()

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def apply(self, day: str, adjustments: Dict[str, Any], consensus: Dict[str, Any]) -> Dict[str, Any]:
        policy = self.store.load()
        policy["entry_confidence_shift"] = self._clamp(float(adjustments.get("entry_confidence_shift", policy["entry_confidence_shift"])), -0.08, 0.08)
        policy["size_multiplier_bias"] = self._clamp(float(adjustments.get("size_multiplier_bias", policy["size_multiplier_bias"])), settings.adaptive_size_floor, settings.adaptive_size_ceiling)
        policy["leverage_bias"] = self._clamp(float(adjustments.get("leverage_bias", policy["leverage_bias"])), 0.7, 1.4)
        policy["breakout_bias"] = self._clamp(float(adjustments.get("breakout_bias", policy["breakout_bias"])), -0.2, 0.2)
        policy["trend_follow_bias"] = self._clamp(float(adjustments.get("trend_follow_bias", policy["trend_follow_bias"])), -0.2, 0.2)
        policy["entry_aggression"] = self._clamp(float(adjustments.get("entry_aggression", policy.get("entry_aggression", 0.0))), -0.2, 0.2)
        policy["breakout_tolerance"] = self._clamp(float(adjustments.get("breakout_tolerance", policy.get("breakout_tolerance", 0.0))), -0.2, 0.2)
        policy["pullback_preference"] = self._clamp(float(adjustments.get("pullback_preference", policy.get("pullback_preference", 0.0))), -0.2, 0.2)
        policy["scale_in_aggression"] = self._clamp(float(adjustments.get("scale_in_aggression", policy.get("scale_in_aggression", 0.0))), -0.2, 0.35)
        policy["scale_out_aggression"] = self._clamp(float(adjustments.get("scale_out_aggression", policy.get("scale_out_aggression", 0.0))), -0.2, 0.35)
        policy["reentry_after_partial"] = self._clamp(float(adjustments.get("reentry_after_partial", policy.get("reentry_after_partial", 0.0))), -0.2, 0.25)
        policy["protection_refresh_bias"] = self._clamp(float(adjustments.get("protection_refresh_bias", policy.get("protection_refresh_bias", 0.0))), -0.2, 0.35)

        protection_profile = str(adjustments.get("protection_profile", policy.get("protection_profile", "balanced")))
        exit_style = str(adjustments.get("exit_style", policy.get("exit_style", "balanced")))
        management_profile = str(adjustments.get("position_management_profile", policy.get("position_management_profile", "balanced")))
        if protection_profile in {"tight", "balanced", "wide"}:
            policy["protection_profile"] = protection_profile
        if exit_style in {"fast", "balanced", "runner"}:
            policy["exit_style"] = exit_style
        if management_profile in {"defensive", "balanced", "press_winners"}:
            policy["position_management_profile"] = management_profile

        policy["initial_stop_loss_atr"] = self._clamp(float(adjustments.get("initial_stop_loss_atr", policy.get("initial_stop_loss_atr", settings.initial_stop_loss_atr))), 1.0, 3.5)
        policy["initial_take_profit_atr"] = self._clamp(float(adjustments.get("initial_take_profit_atr", policy.get("initial_take_profit_atr", settings.initial_take_profit_atr))), 1.2, 5.0)
        policy["break_even_trigger_rr"] = self._clamp(float(adjustments.get("break_even_trigger_rr", policy.get("break_even_trigger_rr", settings.break_even_trigger_rr))), 0.6, 1.8)
        policy["trailing_activation_rr"] = self._clamp(float(adjustments.get("trailing_activation_rr", policy.get("trailing_activation_rr", settings.trailing_activation_rr))), 0.8, 2.5)
        policy["trailing_buffer_atr"] = self._clamp(float(adjustments.get("trailing_buffer_atr", policy.get("trailing_buffer_atr", settings.trailing_buffer_atr))), 0.4, 1.6)
        policy["partial_take_profit_rr"] = self._clamp(float(adjustments.get("partial_take_profit_rr", policy.get("partial_take_profit_rr", settings.lifecycle_partial_take_profit_rr))), 1.0, 3.0)
        policy["break_even_lock_ratio"] = self._clamp(float(adjustments.get("break_even_lock_ratio", policy.get("break_even_lock_ratio", settings.lifecycle_break_even_lock_ratio))), 0.05, 0.5)
        policy["trailing_step_rr"] = self._clamp(float(adjustments.get("trailing_step_rr", policy.get("trailing_step_rr", settings.lifecycle_trailing_step_rr))), 0.2, 0.8)
        policy["tp1_fraction"] = self._clamp(float(adjustments.get("tp1_fraction", policy.get("tp1_fraction", settings.lifecycle_tp1_fraction))), 0.1, 0.5)
        policy["tp2_fraction"] = self._clamp(float(adjustments.get("tp2_fraction", policy.get("tp2_fraction", settings.lifecycle_tp2_fraction))), 0.15, 0.7)
        policy["last_review_day"] = day
        policy["last_review_summary"] = str(adjustments.get("summary", consensus.get("consensus_summary", "")))
        policy["last_review_consensus"] = consensus
        return self.store.save(policy)
