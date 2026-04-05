from typing import Any, Dict, List

from ai.adaptive_policy_store import AdaptivePolicyStore
from ai.model_registry import ModelRegistry
from ai.self_reflection_engine import SelfReflectionEngine
from ai.template_assist import TemplateAssist
from config.settings import settings


class AIAutonomyController:
    def __init__(self) -> None:
        self.registry = ModelRegistry()
        self.reflection = SelfReflectionEngine()
        self.policy_store = AdaptivePolicyStore()
        self.templates = TemplateAssist()

    def autonomy_report(self) -> Dict[str, Any]:
        ratio = self.registry.autonomy_ratio()
        return {
            "autonomy_ratio": ratio,
            "fully_autonomous_by_config": ratio >= settings.autonomy_required_ratio,
            "roles": self.registry.summary(),
        }

    def _policy(self) -> Dict[str, Any]:
        return self.policy_store.load()

    def decide_entry(self, features: Dict[str, Any]) -> Dict[str, Any]:
        policy = self._policy()
        template_view = self.templates.build(features)

        score = float(features.get("ensemble_confidence", 0.5) or 0.5)
        feature_strength = float(features.get("feature_strength", 0.0) or 0.0)
        trend = str(features.get("trend_bias", "range"))
        breakout = float(features.get("pre_breakout_score", 0.0) or 0.0)
        long_context_score = float(features.get("long_context_score", 0.0) or 0.0)
        short_context_score = float(features.get("short_context_score", 0.0) or 0.0)
        template_long = float(template_view.get("template_long_bias", 0.0))
        template_short = float(template_view.get("template_short_bias", 0.0))
        observe_bias = float(template_view.get("template_observe_bias", 0.0))
        breakout_bias = float(policy.get("breakout_bias", 0.0))
        trend_follow_bias = float(policy.get("trend_follow_bias", 0.0))
        entry_aggression = float(policy.get("entry_aggression", 0.0))

        effective_threshold = max(
            settings.adaptive_min_trade_confidence_floor,
            min(
                settings.adaptive_min_trade_confidence_ceiling,
                settings.min_trade_confidence + float(policy.get("entry_confidence_shift", 0.0)) - entry_aggression * 0.04,
            ),
        )

        directional_long = score * 0.42 + feature_strength * 0.14 + long_context_score * 0.16 + template_long * 0.18 + max(0.0, trend_follow_bias) * 0.05 + max(0.0, breakout_bias) * 0.05
        directional_short = score * 0.42 + feature_strength * 0.14 + short_context_score * 0.16 + template_short * 0.18 + max(0.0, -trend_follow_bias) * 0.05 + max(0.0, breakout + min(0.0, breakout_bias)) * 0.05
        side = "long" if directional_long >= directional_short else "short"

        if trend == "bullish" and directional_long >= directional_short * 0.9:
            side = "long"
        elif trend == "bearish" and directional_short >= directional_long * 0.9:
            side = "short"

        entry_score = score * 0.60 + feature_strength * 0.14 + max(directional_long, directional_short) * 0.12 - observe_bias * 0.08 + breakout * (0.08 + breakout_bias * 0.06) + entry_aggression * 0.05
        action = "enter" if entry_score >= effective_threshold else "wait"
        return {
            "action": action,
            "side": side,
            "confidence": round(entry_score, 6),
            "raw_confidence": score,
            "effective_threshold": round(effective_threshold, 4),
            "template_summary": template_view.get("template_summary", ""),
            "market_basis_snapshot": template_view.get("market_basis_snapshot", {}),
            "market_basis_categories": template_view.get("market_basis_categories", []),
        }

    def decide_sizing(self, features: Dict[str, Any]) -> Dict[str, Any]:
        policy = self._policy()
        conf = float(features.get("ensemble_confidence", 0.5) or 0.5)
        breakout = float(features.get("pre_breakout_score", 0.0) or 0.0)
        trend = str(features.get("trend_bias", "range"))
        feature_strength = float(features.get("feature_strength", 0.0) or 0.0)
        volume_ratio = float(features.get("volume_ratio", 1.0) or 1.0)
        entry_aggression = float(policy.get("entry_aggression", 0.0))
        pullback_preference = float(policy.get("pullback_preference", 0.0))

        base = 0.72 + conf * 0.62 + breakout * 0.16 + feature_strength * 0.26 + min(0.18, max(0.0, volume_ratio - 1.0) * 0.2) + entry_aggression * 0.12
        if trend in {"bullish", "bearish"}:
            base += 0.08
        if trend == "range":
            base -= max(0.0, pullback_preference) * 0.05
        size_multiplier = base * float(policy.get("size_multiplier_bias", 1.0))
        size_multiplier = max(settings.adaptive_size_floor, min(settings.adaptive_size_ceiling, size_multiplier))

        if size_multiplier >= 1.35:
            mode = "aggressive"
        elif size_multiplier >= 0.95:
            mode = "normal"
        else:
            mode = "light"
        return {"size_mode": mode, "size_multiplier": round(size_multiplier, 4)}

    def decide_leverage(self, features: Dict[str, Any]) -> Dict[str, Any]:
        policy = self._policy()
        conf = float(features.get("ensemble_confidence", 0.5) or 0.5)
        atr_ratio = float(features.get("atr_ratio", 0.0) or 0.0)
        breakout = float(features.get("pre_breakout_score", 0.0) or 0.0)
        feature_strength = float(features.get("feature_strength", 0.0) or 0.0)
        entry_aggression = float(policy.get("entry_aggression", 0.0))

        base = settings.default_leverage_min + int((settings.default_leverage_max - settings.default_leverage_min) * min(1.0, conf * 0.52 + breakout * 0.15 + feature_strength * 0.28 + max(0.0, entry_aggression) * 0.05))
        if atr_ratio > 0.03:
            base = max(settings.adaptive_leverage_floor, base - 3)
        leverage = int(max(settings.adaptive_leverage_floor, min(settings.adaptive_leverage_ceiling, round(base * float(policy.get("leverage_bias", 1.0))))))

        margin_pct = settings.default_margin_pct_min + (settings.default_margin_pct_max - settings.default_margin_pct_min) * min(1.0, conf * 0.52 + feature_strength * 0.42 + max(0.0, entry_aggression) * 0.06)
        margin_pct *= float(policy.get("size_multiplier_bias", 1.0)) ** 0.35
        margin_pct = max(settings.default_margin_pct_min, min(settings.default_margin_pct_max, margin_pct))
        return {"leverage": leverage, "margin_pct": round(margin_pct, 5)}

    def decide_protection(self, position: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
        policy = self._policy()
        pnl = float(position.get("upl_ratio", position.get("uplRatio", 0.0)) or 0.0)
        breakout = float(features.get("pre_breakout_score", 0.0) or 0.0)
        profile = str(policy.get("protection_profile", "balanced"))
        be_rr = float(policy.get("break_even_trigger_rr", settings.break_even_trigger_rr))
        trail_rr = float(policy.get("trailing_activation_rr", settings.trailing_activation_rr))
        buffer_atr = float(policy.get("trailing_buffer_atr", settings.trailing_buffer_atr))
        refresh_bias = float(policy.get("protection_refresh_bias", 0.0))
        partial_rr = float(policy.get("partial_take_profit_rr", settings.lifecycle_partial_take_profit_rr))
        break_even_lock_ratio = float(policy.get("break_even_lock_ratio", settings.lifecycle_break_even_lock_ratio))
        trailing_step_rr = float(policy.get("trailing_step_rr", settings.lifecycle_trailing_step_rr))

        if profile == "tight":
            be_rr -= 0.12
            trail_rr -= 0.18
            buffer_atr *= 0.82
        elif profile == "wide":
            be_rr += 0.12
            trail_rr += 0.18
            buffer_atr *= 1.15

        buffer_atr *= max(0.75, 1.0 - refresh_bias * 0.35)
        break_even = pnl >= settings.min_lock_profit_pct * max(0.7, be_rr) or breakout >= be_rr * 0.5
        trailing = pnl >= settings.min_lock_profit_pct * max(1.0, trail_rr) or breakout >= trail_rr * 0.55
        tp_stage_1 = pnl >= settings.min_lock_profit_pct * max(1.0, partial_rr)
        tp_stage_2 = pnl >= settings.min_lock_profit_pct * max(1.25, partial_rr + trailing_step_rr)
        refresh_protection = break_even or trailing or tp_stage_1 or tp_stage_2
        return {
            "break_even": break_even,
            "trailing": trailing,
            "tp_stage_1": tp_stage_1,
            "tp_stage_2": tp_stage_2,
            "trailing_buffer_atr": round(buffer_atr, 4),
            "protection_profile": profile,
            "refresh_protection": refresh_protection,
            "break_even_lock_ratio": round(break_even_lock_ratio, 4),
            "trailing_step_rr": round(trailing_step_rr, 4),
        }

    def decide_position_management(self, position: Dict[str, Any], features: Dict[str, Any], protection: Dict[str, Any]) -> Dict[str, Any]:
        policy = self._policy()
        pnl = float(position.get("upl_ratio", position.get("uplRatio", 0.0)) or 0.0)
        side = str(position.get("side", ""))
        trend = str(features.get("trend_bias", "range"))
        breakout = float(features.get("pre_breakout_score", 0.0) or 0.0)
        conf = float(features.get("ensemble_confidence", 0.5) or 0.5)
        liquidity_sweep = float(features.get("liquidity_sweep_score", 0.0) or 0.0)
        feature_strength = float(features.get("feature_strength", 0.0) or 0.0)
        profile = str(policy.get("position_management_profile", "balanced"))
        scale_in_aggression = float(policy.get("scale_in_aggression", 0.0))
        scale_out_aggression = float(policy.get("scale_out_aggression", 0.0))
        reentry_after_partial = float(policy.get("reentry_after_partial", 0.0))
        tp1_fraction = float(policy.get("tp1_fraction", settings.lifecycle_tp1_fraction))
        tp2_fraction = float(policy.get("tp2_fraction", settings.lifecycle_tp2_fraction))
        state = position.get("lifecycle_state", {}) or {}
        has_scale_room = int(state.get("scale_in_count", 0) or 0) < settings.lifecycle_max_scale_ins_per_position
        has_partial_room = int(state.get("partial_exit_count", 0) or 0) < settings.lifecycle_max_partial_exits_per_position
        tp1_done = bool(state.get("tp1_done", False))
        tp2_done = bool(state.get("tp2_done", False))

        aligned = (side == "long" and trend == "bullish") or (side == "short" and trend == "bearish")
        add_score = conf * 0.35 + feature_strength * 0.22 + breakout * 0.18 + max(0.0, pnl) * 18.0 + max(0.0, scale_in_aggression) * 0.12
        reduce_score = (0.45 - conf) * 0.28 + max(0.0, -pnl) * 24.0 + liquidity_sweep * 0.16 + max(0.0, scale_out_aggression) * 0.18
        if aligned:
            add_score += 0.12
        if trend == "range":
            reduce_score += 0.1
            add_score -= 0.08
        if protection.get("trailing"):
            reduce_score += 0.05

        if protection.get("tp_stage_2") and not tp2_done and has_partial_room:
            return {
                "action": "partial_take_profit",
                "fraction": round(min(0.7, max(0.18, tp2_fraction + max(0.0, scale_out_aggression) * 0.10)), 4),
                "reason": "tp_stage_2_lock_in",
                "profile": profile,
                "lifecycle_stage": "tp2",
            }
        if protection.get("tp_stage_1") and not tp1_done and has_partial_room:
            return {
                "action": "partial_take_profit",
                "fraction": round(min(0.55, max(0.12, tp1_fraction + max(0.0, scale_out_aggression) * 0.08)), 4),
                "reason": "tp_stage_1_lock_in",
                "profile": profile,
                "lifecycle_stage": "tp1",
            }
        if has_scale_room and aligned and pnl > settings.min_lock_profit_pct * max(0.9, 0.9 - reentry_after_partial * 0.2) and add_score >= settings.lifecycle_add_threshold:
            return {
                "action": "scale_in",
                "fraction": round(min(settings.max_add_position_multiplier, max(0.12, settings.lifecycle_add_fraction + max(0.0, scale_in_aggression) * 0.2)), 4),
                "reason": "trend_follow_scale_in",
                "profile": profile,
                "lifecycle_stage": "add",
            }
        if has_partial_room and (pnl < -settings.min_lock_profit_pct * 0.7 or reduce_score >= settings.lifecycle_reduce_threshold):
            return {
                "action": "reduce_risk",
                "fraction": round(min(0.5, max(0.12, settings.lifecycle_reduce_fraction + max(0.0, scale_out_aggression) * 0.15)), 4),
                "reason": "risk_reduction_signal",
                "profile": profile,
                "lifecycle_stage": "reduce",
            }
        if profile == "press_winners" and aligned and pnl > settings.min_lock_profit_pct * 1.35 and has_scale_room:
            return {
                "action": "scale_in",
                "fraction": round(min(settings.max_add_position_multiplier, 0.22 + max(0.0, scale_in_aggression) * 0.18), 4),
                "reason": "press_winner_profile",
                "profile": profile,
                "lifecycle_stage": "press",
            }
        return {"action": "hold", "fraction": 0.0, "reason": "hold_position", "profile": profile, "lifecycle_stage": "hold"}

    def decide_exit(self, position: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
        policy = self._policy()
        force_exit = bool(position.get("force_exit", False))
        pnl = float(position.get("upl_ratio", position.get("uplRatio", 0.0)) or 0.0)
        trend = str(features.get("trend_bias", "range"))
        breakout = float(features.get("pre_breakout_score", 0.0) or 0.0)
        liquidity_sweep = float(features.get("liquidity_sweep_score", 0.0) or 0.0)
        style = str(policy.get("exit_style", "balanced"))

        if force_exit:
            return {"action": "exit", "reason": "force_exit_signal", "exit_style": style}
        if pnl < -settings.hard_stop_loss_pct:
            return {"action": "exit", "reason": "hard_stop_loss", "exit_style": style}
        if style == "fast":
            if pnl > settings.min_lock_profit_pct * 1.7 and trend == "range":
                return {"action": "partial_exit", "reason": "fast_range_take_profit", "exit_style": style}
            if pnl > settings.min_lock_profit_pct * 2.1 and breakout < 0.22:
                return {"action": "exit", "reason": "fast_momentum_fade", "exit_style": style}
        elif style == "runner":
            if pnl > settings.min_lock_profit_pct * 3.2 and breakout < 0.18 and liquidity_sweep > 0.62:
                return {"action": "exit", "reason": "runner_exhaustion_exit", "exit_style": style}
        else:
            if pnl > settings.min_lock_profit_pct * 2.2 and trend == "range":
                return {"action": "partial_exit", "reason": "range_take_profit", "exit_style": style}
            if pnl > settings.min_lock_profit_pct * 2.8 and breakout < 0.25 and liquidity_sweep > 0.55:
                return {"action": "exit", "reason": "post_expansion_exhaustion", "exit_style": style}
        return {"action": "hold", "reason": "trend_can_continue", "exit_style": style}

    def reflect(self, recent_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.reflection.reflect(recent_results)
