from typing import Dict
import pandas as pd


class RegimeDetector:
    def detect(self, df: pd.DataFrame, technical_features: Dict[str, float], breakout_features: Dict[str, float]) -> Dict[str, str | float]:
        if df.empty or len(df) < 50:
            return {"market_regime": "unknown", "regime_confidence": 0.0}
        breakout = float(breakout_features.get("pre_breakout_score", 0.0) or 0.0)
        squeeze = float(technical_features.get("boll_squeeze_score", 0.0) or 0.0)
        atr_ratio = float(technical_features.get("atr_ratio", 0.0) or 0.0)
        adx = float(technical_features.get("adx", 0.0) or 0.0)
        volume_ratio = float(technical_features.get("volume_ratio", 1.0) or 1.0)

        if breakout > 0.62 and squeeze > 0.45:
            return {"market_regime": "compression_breakout", "regime_confidence": 0.82}
        if adx >= 24 and atr_ratio >= 0.012:
            return {"market_regime": "trend_expansion", "regime_confidence": 0.76}
        if atr_ratio >= 0.028 and volume_ratio >= 1.25:
            return {"market_regime": "high_volatility", "regime_confidence": 0.74}
        if adx < 17 and squeeze < 0.42:
            return {"market_regime": "range_rotation", "regime_confidence": 0.68}
        return {"market_regime": "general", "regime_confidence": 0.55}
