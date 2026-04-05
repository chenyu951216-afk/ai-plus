from typing import Dict
import numpy as np
import pandas as pd


class TrendAnalyzer:
    def analyze(self, df: pd.DataFrame) -> Dict[str, float | str]:
        if df.empty or len(df) < 60:
            return {
                "trend_bias": "unknown",
                "trend_strength": 0.0,
                "ema_alignment_score": 0.0,
                "slope_ema20": 0.0,
            }
        close = df["close"]
        ema20_s = close.ewm(span=20, adjust=False).mean()
        ema50_s = close.ewm(span=50, adjust=False).mean()
        ema100_s = close.ewm(span=100, adjust=False).mean()
        ema20 = float(ema20_s.iloc[-1])
        ema50 = float(ema50_s.iloc[-1])
        ema100 = float(ema100_s.iloc[-1])
        last = float(close.iloc[-1])
        if last > ema20 > ema50 > ema100:
            bias = "bullish"
            alignment = 1.0
        elif last < ema20 < ema50 < ema100:
            bias = "bearish"
            alignment = 1.0
        elif last > ema20 > ema50:
            bias = "bullish"
            alignment = 0.75
        elif last < ema20 < ema50:
            bias = "bearish"
            alignment = 0.75
        else:
            bias = "range"
            alignment = 0.35
        slope_ema20 = float((ema20_s.iloc[-1] - ema20_s.iloc[-6]) / max(last, 1e-9)) if len(ema20_s) > 6 else 0.0
        strength = float(np.clip(abs(ema20 - ema50) / max(last, 1e-9) + abs(slope_ema20) * 5, 0.0, 1.0))
        return {
            "trend_bias": bias,
            "trend_strength": strength,
            "ema_alignment_score": float(alignment),
            "slope_ema20": slope_ema20,
        }
