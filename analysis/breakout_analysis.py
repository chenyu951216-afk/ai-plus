from typing import Dict
import numpy as np
import pandas as pd


class BreakoutAnalyzer:
    def analyze(self, df: pd.DataFrame) -> Dict[str, float]:
        if df.empty or len(df) < 40:
            return {
                "pre_breakout_score": 0.0,
                "structure_break_score": 0.0,
                "liquidity_sweep_score": 0.0,
            }
        recent = df.tail(20)
        older = df.tail(40).head(20)
        recent_range = float((recent["high"] - recent["low"]).mean())
        older_range = float((older["high"] - older["low"]).mean()) if not older.empty else recent_range
        compression = 0.0 if older_range <= 0 else 1.0 - min(recent_range / older_range, 1.0)

        recent_vol = float(recent["volume"].tail(4).mean())
        base_vol = float(max(recent["volume"].head(10).mean(), 1e-9))
        vol_pressure = float(np.clip(recent_vol / base_vol - 1.0, -1.0, 1.0))

        high_lookback = float(df["high"].tail(20).max())
        low_lookback = float(df["low"].tail(20).min())
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        structure_break = 0.0
        if last_close > high_lookback * 0.998 and last_close > prev_close:
            structure_break = min(1.0, (last_close / max(high_lookback, 1e-9) - 0.998) * 60 + max(vol_pressure, 0.0) * 0.3)
        elif last_close < low_lookback * 1.002 and last_close < prev_close:
            structure_break = min(1.0, (1.002 - last_close / max(low_lookback, 1e-9)) * 60 + max(vol_pressure, 0.0) * 0.3)

        upper_wick = float(df["high"].iloc[-1] - max(df["close"].iloc[-1], df["open"].iloc[-1]))
        lower_wick = float(min(df["close"].iloc[-1], df["open"].iloc[-1]) - df["low"].iloc[-1])
        candle_range = max(float(df["high"].iloc[-1] - df["low"].iloc[-1]), 1e-9)
        liquidity_sweep = np.clip(max(upper_wick, lower_wick) / candle_range + abs(last_close - prev_close) / max(last_close, 1e-9), 0.0, 1.0)

        return {
            "pre_breakout_score": float(np.clip(compression * 0.5 + max(vol_pressure, 0.0) * 0.3 + structure_break * 0.2, 0.0, 1.0)),
            "structure_break_score": float(np.clip(structure_break, 0.0, 1.0)),
            "liquidity_sweep_score": float(liquidity_sweep),
        }
