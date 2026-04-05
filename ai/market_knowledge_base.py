from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class MarketTemplate:
    name: str
    category: str
    side_hint: str
    weight: float
    description: str


class MarketKnowledgeBase:
    """
    提供全市場常見的基礎型態 / 基礎趨勢 / 基礎波動狀態，
    只作為 AI 參考資料，不直接形成硬性下單限制。
    """

    def __init__(self) -> None:
        self.templates: List[MarketTemplate] = [
            MarketTemplate("trend_continuation_long", "trend", "long", 0.22, "多頭趨勢延續"),
            MarketTemplate("trend_continuation_short", "trend", "short", 0.22, "空頭趨勢延續"),
            MarketTemplate("trend_pullback_long", "trend", "long", 0.18, "多頭回踩續漲"),
            MarketTemplate("trend_pullback_short", "trend", "short", 0.18, "空頭反彈續跌"),
            MarketTemplate("compression_breakout_long", "breakout", "long", 0.24, "壓縮後向上突破"),
            MarketTemplate("compression_breakout_short", "breakout", "short", 0.24, "壓縮後向下突破"),
            MarketTemplate("range_mean_revert_long", "range", "long", 0.12, "區間低位反彈"),
            MarketTemplate("range_mean_revert_short", "range", "short", 0.12, "區間高位回落"),
            MarketTemplate("failed_breakout_fade_short", "trap", "short", 0.16, "向上假突破回落"),
            MarketTemplate("failed_breakdown_fade_long", "trap", "long", 0.16, "向下假跌破反彈"),
            MarketTemplate("momentum_expansion_long", "momentum", "long", 0.18, "放量動能延續上攻"),
            MarketTemplate("momentum_expansion_short", "momentum", "short", 0.18, "放量動能延續下殺"),
            MarketTemplate("exhaustion_reversal_short", "reversal", "short", 0.14, "高位過熱衰竭"),
            MarketTemplate("exhaustion_reversal_long", "reversal", "long", 0.14, "低位超跌反彈"),
            MarketTemplate("high_volatility_event_follow", "volatility", "follow_flow", 0.11, "高波動順勢處理"),
            MarketTemplate("low_volatility_coil", "volatility", "observe", 0.09, "低波動盤整待選邊"),
            MarketTemplate("liquidity_sweep_reclaim_long", "liquidity", "long", 0.17, "掃流動性後收回"),
            MarketTemplate("liquidity_sweep_reject_short", "liquidity", "short", 0.17, "掃高點後轉弱"),
            MarketTemplate("structure_break_long", "structure", "long", 0.20, "結構轉強"),
            MarketTemplate("structure_break_short", "structure", "short", 0.20, "結構轉弱"),
        ]

    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        trend = str(features.get("trend_bias", "range"))
        regime = str(features.get("market_regime", "general"))
        breakout = float(features.get("pre_breakout_score", 0.0) or 0.0)
        rsi = float(features.get("rsi", 50.0) or 50.0)
        adx = float(features.get("adx", 0.0) or 0.0)
        atr_ratio = float(features.get("atr_ratio", 0.0) or 0.0)
        volume_ratio = float(features.get("volume_ratio", 1.0) or 1.0)
        momentum = float(features.get("momentum_10", 0.0) or 0.0)
        distance_to_ema20 = float(features.get("distance_to_ema20", 0.0) or 0.0)
        range_position = float(features.get("range_position_20", 0.5) or 0.5)
        upper_wick_ratio = float(features.get("upper_wick_ratio", 0.0) or 0.0)
        lower_wick_ratio = float(features.get("lower_wick_ratio", 0.0) or 0.0)
        body_ratio = float(features.get("body_ratio", 0.0) or 0.0)
        structure_break = float(features.get("structure_break_score", 0.0) or 0.0)
        liquidity_sweep = float(features.get("liquidity_sweep_score", 0.0) or 0.0)

        matched: List[Dict[str, Any]] = []

        def add(name: str, score: float) -> None:
            template = next((t for t in self.templates if t.name == name), None)
            if not template or score <= 0:
                return
            confidence = max(0.0, min(1.0, score))
            matched.append({
                "name": template.name,
                "category": template.category,
                "side_hint": template.side_hint,
                "weight": round(template.weight * confidence, 4),
                "confidence": round(confidence, 4),
                "description": template.description,
            })

        if trend == "bullish" and adx >= 18:
            add("trend_continuation_long", 0.45 + min(0.4, adx / 100.0) + max(0.0, momentum) * 1.5)
        if trend == "bearish" and adx >= 18:
            add("trend_continuation_short", 0.45 + min(0.4, adx / 100.0) + max(0.0, -momentum) * 1.5)
        if trend == "bullish" and distance_to_ema20 < 0.02 and breakout < 0.55:
            add("trend_pullback_long", 0.35 + max(0.0, 0.02 - distance_to_ema20) * 10)
        if trend == "bearish" and abs(distance_to_ema20) < 0.02 and breakout < 0.55:
            add("trend_pullback_short", 0.35 + max(0.0, 0.02 - abs(distance_to_ema20)) * 10)
        if regime == "compression_breakout" and trend == "bullish":
            add("compression_breakout_long", breakout + volume_ratio * 0.1)
        if regime == "compression_breakout" and trend == "bearish":
            add("compression_breakout_short", breakout + volume_ratio * 0.1)
        if trend == "range" and 0.15 <= range_position <= 0.35 and rsi <= 45:
            add("range_mean_revert_long", 0.35 + (0.4 - range_position))
        if trend == "range" and 0.65 <= range_position <= 0.85 and rsi >= 55:
            add("range_mean_revert_short", 0.35 + (range_position - 0.6))
        if breakout >= 0.45 and upper_wick_ratio >= 0.45 and body_ratio < 0.45 and range_position >= 0.75:
            add("failed_breakout_fade_short", 0.4 + upper_wick_ratio * 0.6)
        if breakout >= 0.45 and lower_wick_ratio >= 0.45 and body_ratio < 0.45 and range_position <= 0.25:
            add("failed_breakdown_fade_long", 0.4 + lower_wick_ratio * 0.6)
        if volume_ratio >= 1.35 and momentum > 0.01:
            add("momentum_expansion_long", 0.4 + min(0.35, volume_ratio / 5) + min(0.2, momentum * 6))
        if volume_ratio >= 1.35 and momentum < -0.01:
            add("momentum_expansion_short", 0.4 + min(0.35, volume_ratio / 5) + min(0.2, abs(momentum) * 6))
        if rsi >= 72 and upper_wick_ratio >= 0.35:
            add("exhaustion_reversal_short", 0.35 + min(0.35, (rsi - 70) / 15))
        if rsi <= 28 and lower_wick_ratio >= 0.35:
            add("exhaustion_reversal_long", 0.35 + min(0.35, (30 - rsi) / 15))
        if atr_ratio >= 0.025:
            add("high_volatility_event_follow", 0.3 + min(0.4, atr_ratio * 12))
        if atr_ratio <= 0.01 and breakout < 0.45:
            add("low_volatility_coil", 0.35 + max(0.0, 0.012 - atr_ratio) * 20)
        if liquidity_sweep >= 0.5 and lower_wick_ratio > upper_wick_ratio:
            add("liquidity_sweep_reclaim_long", 0.35 + liquidity_sweep * 0.5)
        if liquidity_sweep >= 0.5 and upper_wick_ratio > lower_wick_ratio:
            add("liquidity_sweep_reject_short", 0.35 + liquidity_sweep * 0.5)
        if structure_break >= 0.55 and trend == "bullish":
            add("structure_break_long", 0.35 + structure_break * 0.5)
        if structure_break >= 0.55 and trend == "bearish":
            add("structure_break_short", 0.35 + structure_break * 0.5)

        if not matched:
            matched.append({
                "name": "neutral_observation",
                "category": "neutral",
                "side_hint": "none",
                "weight": 0.05,
                "confidence": 0.25,
                "description": "目前沒有明確優勢型態，只供觀察",
            })

        long_bias = sum(x["weight"] for x in matched if x["side_hint"] in {"long"})
        short_bias = sum(x["weight"] for x in matched if x["side_hint"] in {"short"})
        follow_flow = sum(x["weight"] for x in matched if x["side_hint"] in {"follow_flow"})
        observe_bias = sum(x["weight"] for x in matched if x["side_hint"] in {"observe"})
        categories = sorted({x["category"] for x in matched})

        basis_snapshot = {
            "trend": trend,
            "regime": regime,
            "rsi": round(rsi, 4),
            "adx": round(adx, 4),
            "atr_ratio": round(atr_ratio, 6),
            "volume_ratio": round(volume_ratio, 4),
            "momentum_10": round(momentum, 6),
            "range_position_20": round(range_position, 4),
            "structure_break_score": round(structure_break, 4),
            "liquidity_sweep_score": round(liquidity_sweep, 4),
            "pre_breakout_score": round(breakout, 4),
        }

        return {
            "market_basis_templates": matched[:8],
            "market_basis_snapshot": basis_snapshot,
            "market_basis_categories": categories,
            "market_long_bias": round(long_bias + follow_flow * 0.5, 4),
            "market_short_bias": round(short_bias + follow_flow * 0.5, 4),
            "market_observe_bias": round(observe_bias, 4),
            "market_basis_summary": ", ".join(x["name"] for x in matched[:6]),
        }
