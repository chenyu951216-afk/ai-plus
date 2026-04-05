from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional
from clients.okx_client import OKXClient
from config.settings import settings

class LivePreflightService:
    def __init__(self) -> None:
        self.client = OKXClient()
        self.instrument_cache: dict[str, Dict[str, Any]] = {}

    def load_instrument(self, inst_id: str) -> Optional[Dict[str, Any]]:
        if inst_id in self.instrument_cache:
            return self.instrument_cache[inst_id]
        for row in self.client.safe_get_instruments():
            if row.get("instId") == inst_id:
                self.instrument_cache[inst_id] = row
                return row
        return None

    def quantize_down(self, value: float, step: str) -> float:
        if not step or Decimal(step) == 0:
            return value
        d_value = Decimal(str(value))
        d_step = Decimal(str(step))
        quantized = (d_value / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
        return float(quantized)

    def preflight(self, inst_id: str, desired_size: float, desired_price: float | None) -> Dict[str, Any]:
        instrument = self.load_instrument(inst_id)
        if not instrument:
            return {"ok": False, "reason": "instrument_not_found"}

        lot_sz = instrument.get("lotSz", "1")
        min_sz = instrument.get("minSz", "1")
        tick_sz = instrument.get("tickSz", "0.1")

        size = self.quantize_down(desired_size, lot_sz)
        if size < float(min_sz):
            size = float(min_sz)

        price = self.quantize_down(desired_price, tick_sz) if desired_price is not None else None

        max_avail = None
        if settings.require_max_avail_check:
            max_payload = self.client.safe_get_max_avail_size(inst_id, settings.td_mode)
            for row in max_payload.get("data", []):
                try:
                    max_avail = float(row.get("availBuy") or row.get("availSell") or 0.0)
                    break
                except (TypeError, ValueError):
                    pass
        if max_avail is not None and max_avail > 0:
            size = min(size, max_avail)

        if size <= 0:
            return {"ok": False, "reason": "size_after_preflight_invalid"}

        return {"ok": True, "inst_id": inst_id, "lot_sz": lot_sz, "min_sz": min_sz, "tick_sz": tick_sz, "final_size": size, "final_price": price, "max_avail": max_avail}


# Backward-compatible alias used by the runtime service.
PreflightService = LivePreflightService
