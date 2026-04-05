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

    def _extract_max_avail(self, payload: Dict[str, Any]) -> float | None:
        for row in payload.get("data", []):
            try:
                return float(row.get("availBuy") or row.get("availSell") or 0.0)
            except (TypeError, ValueError):
                continue
        return None

    def _max_avail_with_fallback(self, inst_id: str) -> Dict[str, Any]:
        """
        Some OKX account modes reject /account/max-avail-size with 51010.
        In that case we degrade gracefully instead of spamming errors and blocking all scans.
        """
        payload = self.client.safe_get_max_avail_size(inst_id, settings.td_mode)

        # normal success
        max_avail = self._extract_max_avail(payload)
        if max_avail is not None:
            return {
                "supported": True,
                "max_avail": max_avail,
                "reason": "ok",
            }

        # API wrapper returns {"code":"-1","data":[]} on exception,
        # or a runtime payload if the server answered with non-zero code.
        msg = str(payload.get("msg", "")).lower()
        code = str(payload.get("code", ""))

        # current account mode not compatible with this check
        if code == "51010" or "current account mode" in msg:
            return {
                "supported": False,
                "max_avail": None,
                "reason": "max_avail_unsupported_for_account_mode",
            }

        # generic unavailable/fallback
        return {
            "supported": False,
            "max_avail": None,
            "reason": "max_avail_unavailable",
        }

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
        max_avail_reason = "not_checked"

        if settings.require_max_avail_check:
            max_row = self._max_avail_with_fallback(inst_id)
            max_avail = max_row.get("max_avail")
            max_avail_reason = max_row.get("reason", "unknown")

        if max_avail is not None and max_avail > 0:
            size = min(size, max_avail)

        if size <= 0:
            return {
                "ok": False,
                "reason": "size_after_preflight_invalid",
                "max_avail_reason": max_avail_reason,
            }

        return {
            "ok": True,
            "inst_id": inst_id,
            "lot_sz": lot_sz,
            "min_sz": min_sz,
            "tick_sz": tick_sz,
            "final_size": size,
            "final_price": price,
            "max_avail": max_avail,
            "max_avail_reason": max_avail_reason,
        }

    def check(self, candidate: Dict[str, Any], account_summary: Dict[str, Any], pos_mode: str) -> Dict[str, Any]:
        symbol = candidate["symbol"]
        market_snapshot = candidate.get("market_snapshot", {}) or {}
        leverage_decision = candidate.get("leverage_decision", {}) or {}
        sizing_decision = candidate.get("sizing_decision", {}) or {}

        leverage = int(leverage_decision.get("leverage", settings.default_leverage_min))
        margin_pct = float(leverage_decision.get("margin_pct", settings.default_margin_pct_min))
        size_multiplier = float(sizing_decision.get("size_multiplier", 1.0) or 1.0)
        last_price = float(market_snapshot.get("last_price", 0.0) or 0.0)
        available_usdt = float(account_summary.get("available_equity", account_summary.get("equity", 0.0)) or 0.0)

        desired_margin = max(available_usdt * margin_pct * size_multiplier, 1.0)
        desired_notional = desired_margin * max(leverage, 1)
        desired_size = round(max(desired_notional / max(last_price, 1e-9), settings.lifecycle_min_position_size), 8)

        result = self.preflight(symbol, desired_size, last_price)
        if result.get("ok"):
            return {
                "blocked": False,
                "reason": result.get("max_avail_reason", "ok"),
                "final_size": result.get("final_size"),
                "final_price": result.get("final_price"),
                "max_avail": result.get("max_avail"),
                "max_avail_reason": result.get("max_avail_reason", "ok"),
            }

        return {
            "blocked": True,
            "reason": result.get("reason", "preflight_failed"),
            "max_avail_reason": result.get("max_avail_reason", "unknown"),
        }


PreflightService = LivePreflightService
