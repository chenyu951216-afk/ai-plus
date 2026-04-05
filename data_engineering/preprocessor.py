from typing import Any, List
import numpy as np
import pandas as pd

class DataPreprocessor:
    def candles_to_dataframe(self, raw_candles: List[List[Any]]) -> pd.DataFrame:
        if not raw_candles:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(raw_candles, columns=["ts","open","high","low","close","volume","vol_ccy","vol_quote","confirm"])
        df = df[["ts","open","high","low","close","volume"]].copy()
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["ts"] = pd.to_datetime(pd.to_numeric(df["ts"], errors="coerce"), unit="ms", utc=True)
        df = df.sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
        df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().dropna().reset_index(drop=True)
        return df
