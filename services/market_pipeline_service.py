import time
from typing import Any, Dict, List
from clients.okx_client import OKXClient
from config.settings import settings
from data_engineering.preprocessor import DataPreprocessor

class MarketPipelineService:
    def __init__(self) -> None:
        self.client = OKXClient()
        self.pre = DataPreprocessor()

    def get_top_symbols(self) -> List[Dict[str, Any]]:
        tickers = self.client.safe_get_tickers()
        instruments = self.client.safe_get_instruments()
        live_ids = {x["instId"] for x in instruments if x.get("state") == "live"}
        rows = []
        for x in tickers:
            inst_id = x.get("instId", "")
            if inst_id not in live_ids or "-USDT-" not in inst_id:
                continue
            try:
                rows.append({"instId": inst_id, "last_price": float(x.get("last", 0.0)), "quote_volume": float(x.get("volCcy24h", 0.0))})
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda r: r["quote_volume"], reverse=True)
        return rows[:settings.scan_top_n]

    def scan(self, symbols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for s in symbols:
            raw = self.client.safe_get_candles(s["instId"], settings.primary_timeframe, settings.candle_limit)
            out.append({"symbol": s["instId"], "market_snapshot": s, "df": self.pre.candles_to_dataframe(raw)})
            time.sleep(settings.scan_symbol_interval_sec)
        return out
