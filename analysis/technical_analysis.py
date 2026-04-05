from typing import Dict
import numpy as np
import pandas as pd


class TechnicalAnalyzer:
    def _atr(self, df: pd.DataFrame, period: int = 14) -> float:
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if pd.notna(atr) else 0.0

    def _rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain.iloc[-1] / max(loss.iloc[-1], 1e-9)
        return float(100 - (100 / (1 + rs))) if pd.notna(rs) else 50.0

    def _adx(self, df: pd.DataFrame, period: int = 14) -> float:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
        adx = dx.rolling(period).mean().iloc[-1]
        return float(adx) if pd.notna(adx) else 0.0

    def analyze(self, df: pd.DataFrame) -> Dict[str, float]:
        if df.empty or len(df) < 60:
            return {
                "atr": 0.0,
                "atr_ratio": 0.0,
                "boll_squeeze_score": 0.0,
                "rsi": 50.0,
                "adx": 0.0,
                "volume_ratio": 1.0,
                "momentum_10": 0.0,
                "distance_to_ema20": 0.0,
                "range_position_20": 0.5,
                "body_ratio": 0.0,
                "upper_wick_ratio": 0.0,
                "lower_wick_ratio": 0.0,
            }
        close = df["close"]
        open_ = df["open"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]
        atr = self._atr(df)
        ma = close.rolling(20).mean()
        std = close.rolling(20).std()
        width = float(((ma + 2 * std).iloc[-1] - (ma - 2 * std).iloc[-1]) / max(close.iloc[-1], 1e-9))
        rsi = self._rsi(close)
        adx = self._adx(df)
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        momentum_10 = float(close.iloc[-1] / max(close.iloc[-11], 1e-9) - 1.0) if len(close) > 11 else 0.0
        volume_ratio = float(volume.tail(5).mean() / max(volume.tail(20).mean(), 1e-9))
        hh = float(high.tail(20).max())
        ll = float(low.tail(20).min())
        range_position = (float(close.iloc[-1]) - ll) / max(hh - ll, 1e-9)

        candle_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-9)
        body = abs(float(close.iloc[-1] - open_.iloc[-1]))
        upper_wick = float(high.iloc[-1] - max(close.iloc[-1], open_.iloc[-1]))
        lower_wick = float(min(close.iloc[-1], open_.iloc[-1]) - low.iloc[-1])

        return {
            "atr": atr,
            "atr_ratio": float(atr / max(close.iloc[-1], 1e-9)),
            "boll_squeeze_score": float(np.clip(1.0 - min(width / 0.08, 1.0), 0.0, 1.0)),
            "rsi": float(np.clip(rsi, 0.0, 100.0)),
            "adx": float(np.clip(adx, 0.0, 100.0)),
            "volume_ratio": float(max(0.0, volume_ratio)),
            "momentum_10": momentum_10,
            "distance_to_ema20": float((close.iloc[-1] - ema20) / max(close.iloc[-1], 1e-9)),
            "range_position_20": float(np.clip(range_position, 0.0, 1.0)),
            "body_ratio": float(np.clip(body / candle_range, 0.0, 1.0)),
            "upper_wick_ratio": float(np.clip(max(0.0, upper_wick) / candle_range, 0.0, 1.0)),
            "lower_wick_ratio": float(np.clip(max(0.0, lower_wick) / candle_range, 0.0, 1.0)),
        }
