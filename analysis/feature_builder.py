from typing import Any, Dict


class FeatureBuilder:
    def build(self, symbol: str, market_snapshot: Dict[str, Any], *feature_dicts: Dict[str, Any]) -> Dict[str, Any]:
        merged = {
            "symbol": symbol,
            "last_price": market_snapshot.get("last_price", 0.0),
            "quote_volume_24h": market_snapshot.get("quote_volume_24h", 0.0),
            "change_24h": market_snapshot.get("change_24h", 0.0),
        }
        for item in feature_dicts:
            merged.update(item)

        trend_strength = float(merged.get("trend_strength", 0.0) or 0.0)
        breakout = float(merged.get("pre_breakout_score", 0.0) or 0.0)
        volume_ratio = float(merged.get("volume_ratio", 1.0) or 1.0)
        adx = float(merged.get("adx", 0.0) or 0.0)
        ema_alignment = float(merged.get("ema_alignment_score", 0.0) or 0.0)
        momentum = float(merged.get("momentum_10", 0.0) or 0.0)
        range_position = float(merged.get("range_position_20", 0.5) or 0.5)

        merged["feature_strength"] = round(
            min(1.0, trend_strength * 0.32 + breakout * 0.28 + min(1.0, volume_ratio / 2.0) * 0.12 + min(1.0, adx / 35.0) * 0.12 + ema_alignment * 0.08 + min(1.0, abs(momentum) * 10) * 0.08),
            6,
        )
        merged["long_context_score"] = round(min(1.0, max(0.0, trend_strength * 0.35 + breakout * 0.2 + max(0.0, momentum) * 6 * 0.2 + ema_alignment * 0.15 + max(0.0, 0.5 - range_position) * 0.1)), 6)
        merged["short_context_score"] = round(min(1.0, max(0.0, trend_strength * 0.35 + breakout * 0.2 + max(0.0, -momentum) * 6 * 0.2 + ema_alignment * 0.15 + max(0.0, range_position - 0.5) * 0.1)), 6)
        return merged
