import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from clients.okx_client import OKXClient
from config.settings import settings as global_settings

logger = logging.getLogger("MarketPipelineService")


class MarketPipelineService:
    """
    Preserves the original project shape:
    - can be initialized with or without client/settings
    - get_top_symbols()
    - scan(symbols) -> [{"symbol","df","market_snapshot"}]

    This fixes the crash caused by requiring client/settings positional args,
    while avoiding the overly-simplified version that removed needed behavior.
    """

    def __init__(self, client: Optional[OKXClient] = None, settings_obj: Optional[Any] = None):
        self.client = client or OKXClient()
        self.settings = settings_obj or global_settings

    def _normalize_symbol(self, item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return str(
                item.get("instId")
                or item.get("symbol")
                or item.get("inst_id")
                or item.get("code")
                or ""
            )
        return str(item or "")

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def get_top_symbols(self) -> List[Dict[str, Any]]:
        tickers = self.client.safe_get_tickers() or []
        top_n = int(
            getattr(self.settings, "scan_top_n", None)
            or getattr(self.settings, "top_symbols_limit", None)
            or 50
        )

        rows: List[Dict[str, Any]] = []
        for row in tickers:
            inst_id = str(row.get("instId", ""))
            if not inst_id.endswith("-SWAP"):
                continue

            quote_volume = self._safe_float(
                row.get("volCcy24h", row.get("vol24h", 0.0)),
                0.0,
            )
            last_price = self._safe_float(row.get("last", 0.0), 0.0)
            change_24h = 0.0
            open_24h = self._safe_float(row.get("open24h", 0.0), 0.0)
            if open_24h > 0:
                change_24h = (last_price - open_24h) / open_24h

            rows.append(
                {
                    "instId": inst_id,
                    "symbol": inst_id,
                    "last_price": last_price,
                    "quote_volume": quote_volume,
                    "change_24h": change_24h,
                }
            )

        rows.sort(key=lambda x: x["quote_volume"], reverse=True)
        logger.info("[PIPELINE] selected top symbols count=%s from tickers=%s", min(len(rows), top_n), len(tickers))
        return rows[:top_n]

    def _build_dataframe(self, raw: List[List[Any]]) -> pd.DataFrame:
        parsed: List[Dict[str, Any]] = []
        for c in raw:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            try:
                parsed.append(
                    {
                        "ts": int(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "turnover": float(c[6]) if len(c) > 6 and c[6] not in (None, "") else 0.0,
                    }
                )
            except Exception:
                continue

        df = pd.DataFrame(parsed)
        if df.empty:
            return df

        df = df.sort_values("ts").reset_index(drop=True)
        return df

    def scan(self, symbols: List[Any]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        timeframe = getattr(self.settings, "primary_timeframe", "15m")
        limit = int(getattr(self.settings, "candle_limit", 240) or 240)
        min_rows = max(30, min(limit // 2, 120))

        for item in symbols:
            symbol = self._normalize_symbol(item)
            if not symbol:
                continue

            try:
                raw = self.client.safe_get_candles(symbol, timeframe, limit)
                if not raw:
                    logger.warning("[SCAN] %s no candle data", symbol)
                    continue

                df = self._build_dataframe(raw)
                if df.empty or len(df) < min_rows:
                    logger.warning("[SCAN] %s insufficient candle rows=%s", symbol, len(df))
                    continue

                last_close = self._safe_float(df.iloc[-1]["close"], 0.0)
                prev_close = self._safe_float(df.iloc[-2]["close"], last_close) if len(df) >= 2 else last_close
                change_1 = ((last_close - prev_close) / prev_close) if prev_close else 0.0

                if isinstance(item, dict):
                    market_snapshot = {
                        "symbol": symbol,
                        "last_price": self._safe_float(item.get("last_price", last_close), last_close),
                        "quote_volume": self._safe_float(item.get("quote_volume", 0.0), 0.0),
                        "change_24h": self._safe_float(item.get("change_24h", 0.0), 0.0),
                        "change_1": change_1,
                    }
                else:
                    market_snapshot = {
                        "symbol": symbol,
                        "last_price": last_close,
                        "quote_volume": 0.0,
                        "change_24h": 0.0,
                        "change_1": change_1,
                    }

                results.append(
                    {
                        "symbol": symbol,
                        "df": df,
                        "market_snapshot": market_snapshot,
                    }
                )

                time.sleep(0.02)
            except Exception as exc:
                logger.exception("[SCAN ERROR] %s %s", symbol, exc)
                continue

        return results
