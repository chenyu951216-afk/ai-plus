from __future__ import annotations

from typing import Any, Dict, Tuple

from ai.adaptive_policy_store import AdaptivePolicyStore
from config.settings import settings


class OptimizationApplyService:
    """
    Safety-first application layer for GPT/AI adjustments.

    Goal:
    - prevent small-sample overreaction
    - prevent GPT suggestions from forcing large jumps in policy
    - require at least moderate evidence before changing live behavior
    - degrade gracefully to previous policy when evidence is weak
    """

    def __init__(self) -> None:
        self.store = AdaptivePolicyStore()

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _bounded_step(self, current: float, target: float, max_step: float, low: float, high: float) -> float:
        target = self._clamp(target, low, high)
        if target > current:
            return self._clamp(min(target, current + max_step), low, high)
        return self._clamp(max(target, current - max_step), low, high)

    def _pick_enum(self, candidate: Any, current: str, allowed: set[str]) -> str:
        candidate_str = str(candidate or current)
        return candidate_str if candidate_str in allowed else current

    def _extract_review_stats(self, adjustments: Dict[str, Any], consensus: Dict[str, Any]) -> Dict[str, Any]:
        stats = {}
        for source in (consensus, adjustments):
            if not isinstance(source, dict):
                continue
            for key in (
                "trade_count",
                "win_rate",
                "net_pnl",
                "avg_pnl",
                "max_drawdown",
                "loss_streak",
                "confidence_score",
                "agreement_score",
                "sample_quality",
                "review_quality",
                "risk_alert",
                "market_regime",
                "suspicious_day",
            ):
                if key in source and key not in stats:
                    stats[key] = source[key]
            digest = source.get("digest")
            if isinstance(digest, dict):
                for key in ("trade_count", "win_rate", "net_pnl", "avg_pnl", "max_drawdown", "loss_streak"):
                    if key in digest and key not in stats:
                        stats[key] = digest[key]
        return stats

    def _safety_gate(self, stats: Dict[str, Any], adjustments: Dict[str, Any], consensus: Dict[str, Any]) -> Tuple[str, float, Dict[str, Any]]:
        trade_count = self._safe_int(stats.get("trade_count", 0), 0)
        win_rate = self._safe_float(stats.get("win_rate", 0.5), 0.5)
        max_drawdown = abs(self._safe_float(stats.get("max_drawdown", 0.0), 0.0))
        agreement_score = self._safe_float(
            consensus.get("agreement_score", stats.get("agreement_score", stats.get("confidence_score", 0.5))),
            0.5,
        )
        review_quality = self._safe_float(stats.get("review_quality", stats.get("sample_quality", 0.5)), 0.5)
        suspicious_day = bool(stats.get("suspicious_day", False))
        risk_alert = str(stats.get("risk_alert", "")).lower()

        reasons: list[str] = []

        if trade_count < 6:
            reasons.append("too_few_trades")
        if trade_count < 12:
            reasons.append("small_sample")
        if agreement_score < 0.45:
            reasons.append("weak_gpt_ai_agreement")
        if review_quality < 0.45:
            reasons.append("low_review_quality")
        if suspicious_day:
            reasons.append("suspicious_market_day")
        if "extreme" in risk_alert or "abnormal" in risk_alert:
            reasons.append("extreme_risk_alert")
        if trade_count > 0 and win_rate < 0.25 and max_drawdown > 0.08:
            reasons.append("bad_day_do_not_rewrite_policy")

        # lock = no policy change, cautious = tiny bounded moves only, active = normal bounded moves
        if "too_few_trades" in reasons or "suspicious_market_day" in reasons or "bad_day_do_not_rewrite_policy" in reasons:
            mode = "lock"
            multiplier = 0.0
        elif reasons:
            mode = "cautious"
            multiplier = 0.35
        else:
            mode = "active"
            multiplier = 1.0

        meta = {
            "trade_count": trade_count,
            "win_rate": round(win_rate, 4),
            "max_drawdown": round(max_drawdown, 4),
            "agreement_score": round(agreement_score, 4),
            "review_quality": round(review_quality, 4),
            "mode": mode,
            "reasons": reasons,
        }
        return mode, multiplier, meta

    def apply(self, day: str, adjustments: Dict[str, Any], consensus: Dict[str, Any]) -> Dict[str, Any]:
        policy = self.store.load()
        stats = self._extract_review_stats(adjustments, consensus)
        mode, step_multiplier, safety_meta = self._safety_gate(stats, adjustments, consensus)

        # Keep a record even when policy is locked.
        policy["last_review_day"] = day
        policy["last_review_summary"] = str(adjustments.get("summary", consensus.get("consensus_summary", "")))
        policy["last_review_consensus"] = consensus
        policy["last_safety_mode"] = mode
        policy["last_safety_meta"] = safety_meta

        if mode == "lock":
            return self.store.save(policy)

        # Daily drift guards. These values intentionally keep live changes small.
        core_step = 0.015 * step_multiplier
        bias_step = 0.05 * step_multiplier
        atr_step = 0.18 * step_multiplier
        rr_step = 0.12 * step_multiplier
        fraction_step = 0.06 * step_multiplier
        leverage_step = 0.08 * step_multiplier

        # Core entry / sizing / leverage behavior
        policy["entry_confidence_shift"] = self._bounded_step(
            self._safe_float(policy.get("entry_confidence_shift", 0.0), 0.0),
            self._safe_float(adjustments.get("entry_confidence_shift", policy.get("entry_confidence_shift", 0.0)), 0.0),
            core_step,
            -0.08,
            0.08,
        )
        policy["size_multiplier_bias"] = self._bounded_step(
            self._safe_float(policy.get("size_multiplier_bias", 1.0), 1.0),
            self._safe_float(adjustments.get("size_multiplier_bias", policy.get("size_multiplier_bias", 1.0)), 1.0),
            0.18 * step_multiplier,
            settings.adaptive_size_floor,
            settings.adaptive_size_ceiling,
        )
        policy["leverage_bias"] = self._bounded_step(
            self._safe_float(policy.get("leverage_bias", 1.0), 1.0),
            self._safe_float(adjustments.get("leverage_bias", policy.get("leverage_bias", 1.0)), 1.0),
            leverage_step,
            0.7,
            1.4,
        )
        policy["breakout_bias"] = self._bounded_step(
            self._safe_float(policy.get("breakout_bias", 0.0), 0.0),
            self._safe_float(adjustments.get("breakout_bias", policy.get("breakout_bias", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.2,
        )
        policy["trend_follow_bias"] = self._bounded_step(
            self._safe_float(policy.get("trend_follow_bias", 0.0), 0.0),
            self._safe_float(adjustments.get("trend_follow_bias", policy.get("trend_follow_bias", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.2,
        )
        policy["entry_aggression"] = self._bounded_step(
            self._safe_float(policy.get("entry_aggression", 0.0), 0.0),
            self._safe_float(adjustments.get("entry_aggression", policy.get("entry_aggression", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.2,
        )
        policy["breakout_tolerance"] = self._bounded_step(
            self._safe_float(policy.get("breakout_tolerance", 0.0), 0.0),
            self._safe_float(adjustments.get("breakout_tolerance", policy.get("breakout_tolerance", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.2,
        )
        policy["pullback_preference"] = self._bounded_step(
            self._safe_float(policy.get("pullback_preference", 0.0), 0.0),
            self._safe_float(adjustments.get("pullback_preference", policy.get("pullback_preference", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.2,
        )
        policy["scale_in_aggression"] = self._bounded_step(
            self._safe_float(policy.get("scale_in_aggression", 0.0), 0.0),
            self._safe_float(adjustments.get("scale_in_aggression", policy.get("scale_in_aggression", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.35,
        )
        policy["scale_out_aggression"] = self._bounded_step(
            self._safe_float(policy.get("scale_out_aggression", 0.0), 0.0),
            self._safe_float(adjustments.get("scale_out_aggression", policy.get("scale_out_aggression", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.35,
        )
        policy["reentry_after_partial"] = self._bounded_step(
            self._safe_float(policy.get("reentry_after_partial", 0.0), 0.0),
            self._safe_float(adjustments.get("reentry_after_partial", policy.get("reentry_after_partial", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.25,
        )
        policy["protection_refresh_bias"] = self._bounded_step(
            self._safe_float(policy.get("protection_refresh_bias", 0.0), 0.0),
            self._safe_float(adjustments.get("protection_refresh_bias", policy.get("protection_refresh_bias", 0.0)), 0.0),
            bias_step,
            -0.2,
            0.35,
        )

        # Enumerated fields only change when there is enough trust.
        if mode == "active":
            policy["protection_profile"] = self._pick_enum(
                adjustments.get("protection_profile", policy.get("protection_profile", "balanced")),
                str(policy.get("protection_profile", "balanced")),
                {"tight", "balanced", "wide"},
            )
            policy["exit_style"] = self._pick_enum(
                adjustments.get("exit_style", policy.get("exit_style", "balanced")),
                str(policy.get("exit_style", "balanced")),
                {"fast", "balanced", "runner"},
            )
            policy["position_management_profile"] = self._pick_enum(
                adjustments.get("position_management_profile", policy.get("position_management_profile", "balanced")),
                str(policy.get("position_management_profile", "balanced")),
                {"defensive", "balanced", "press_winners"},
            )

        # Protection and exit behavior: bounded and slow.
        policy["initial_stop_loss_atr"] = self._bounded_step(
            self._safe_float(policy.get("initial_stop_loss_atr", settings.initial_stop_loss_atr), settings.initial_stop_loss_atr),
            self._safe_float(adjustments.get("initial_stop_loss_atr", policy.get("initial_stop_loss_atr", settings.initial_stop_loss_atr)), settings.initial_stop_loss_atr),
            atr_step,
            1.0,
            3.5,
        )
        policy["initial_take_profit_atr"] = self._bounded_step(
            self._safe_float(policy.get("initial_take_profit_atr", settings.initial_take_profit_atr), settings.initial_take_profit_atr),
            self._safe_float(adjustments.get("initial_take_profit_atr", policy.get("initial_take_profit_atr", settings.initial_take_profit_atr)), settings.initial_take_profit_atr),
            atr_step,
            1.2,
            5.0,
        )
        policy["break_even_trigger_rr"] = self._bounded_step(
            self._safe_float(policy.get("break_even_trigger_rr", settings.break_even_trigger_rr), settings.break_even_trigger_rr),
            self._safe_float(adjustments.get("break_even_trigger_rr", policy.get("break_even_trigger_rr", settings.break_even_trigger_rr)), settings.break_even_trigger_rr),
            rr_step,
            0.6,
            1.8,
        )
        policy["trailing_activation_rr"] = self._bounded_step(
            self._safe_float(policy.get("trailing_activation_rr", settings.trailing_activation_rr), settings.trailing_activation_rr),
            self._safe_float(adjustments.get("trailing_activation_rr", policy.get("trailing_activation_rr", settings.trailing_activation_rr)), settings.trailing_activation_rr),
            rr_step,
            0.8,
            2.5,
        )
        policy["trailing_buffer_atr"] = self._bounded_step(
            self._safe_float(policy.get("trailing_buffer_atr", settings.trailing_buffer_atr), settings.trailing_buffer_atr),
            self._safe_float(adjustments.get("trailing_buffer_atr", policy.get("trailing_buffer_atr", settings.trailing_buffer_atr)), settings.trailing_buffer_atr),
            atr_step,
            0.4,
            1.6,
        )
        policy["partial_take_profit_rr"] = self._bounded_step(
            self._safe_float(policy.get("partial_take_profit_rr", settings.lifecycle_partial_take_profit_rr), settings.lifecycle_partial_take_profit_rr),
            self._safe_float(adjustments.get("partial_take_profit_rr", policy.get("partial_take_profit_rr", settings.lifecycle_partial_take_profit_rr)), settings.lifecycle_partial_take_profit_rr),
            rr_step,
            1.0,
            3.0,
        )
        policy["break_even_lock_ratio"] = self._bounded_step(
            self._safe_float(policy.get("break_even_lock_ratio", settings.lifecycle_break_even_lock_ratio), settings.lifecycle_break_even_lock_ratio),
            self._safe_float(adjustments.get("break_even_lock_ratio", policy.get("break_even_lock_ratio", settings.lifecycle_break_even_lock_ratio)), settings.lifecycle_break_even_lock_ratio),
            fraction_step,
            0.05,
            0.5,
        )
        policy["trailing_step_rr"] = self._bounded_step(
            self._safe_float(policy.get("trailing_step_rr", settings.lifecycle_trailing_step_rr), settings.lifecycle_trailing_step_rr),
            self._safe_float(adjustments.get("trailing_step_rr", policy.get("trailing_step_rr", settings.lifecycle_trailing_step_rr)), settings.lifecycle_trailing_step_rr),
            rr_step,
            0.2,
            0.8,
        )
        policy["tp1_fraction"] = self._bounded_step(
            self._safe_float(policy.get("tp1_fraction", settings.lifecycle_tp1_fraction), settings.lifecycle_tp1_fraction),
            self._safe_float(adjustments.get("tp1_fraction", policy.get("tp1_fraction", settings.lifecycle_tp1_fraction)), settings.lifecycle_tp1_fraction),
            fraction_step,
            0.1,
            0.5,
        )
        policy["tp2_fraction"] = self._bounded_step(
            self._safe_float(policy.get("tp2_fraction", settings.lifecycle_tp2_fraction), settings.lifecycle_tp2_fraction),
            self._safe_float(adjustments.get("tp2_fraction", policy.get("tp2_fraction", settings.lifecycle_tp2_fraction)), settings.lifecycle_tp2_fraction),
            fraction_step,
            0.15,
            0.7,
        )

        policy["growth_protection_enabled"] = True
        return self.store.save(policy)
