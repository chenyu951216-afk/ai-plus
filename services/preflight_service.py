from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional

from clients.okx_client import OKXClient
from config.settings import settings


class LivePreflightService:
    def __init__(self) -> None:
        self.client = OKXClient()
        self.instrument_cache: dict[str, Dict[str, Any]] = {}

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, "", "None"):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def load_instrument(self, inst_id: str) -> Optional[Dict[str, Any]]:
        if not inst_id:
            return None
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
        payload = self.client.safe_get_max_avail_size(inst_id, settings.td_mode)

        max_avail = self._extract_max_avail(payload)
        if max_avail is not None:
            return {
                "supported": True,
                "max_avail": max_avail,
                "reason": "ok",
            }

        msg = str(payload.get("msg", "")).lower()
        code = str(payload.get("code", ""))

        if code == "51010" or "current account mode" in msg:
            return {
                "supported": False,
                "max_avail": None,
                "reason": "max_avail_unsupported_for_account_mode",
            }

        return {
            "supported": False,
            "max_avail": None,
            "reason": "max_avail_unavailable",
        }

    def _convert_base_size_to_order_size(self, instrument: Dict[str, Any], desired_size: float) -> float:
        """
        desired_size 在你現在的策略流程裡，是用 notional / last_price 算出的「幣數」。
        但 OKX SWAP/FUTURES 的 sz 通常是「合約張數」，不是幣數。
        所以這裡要先把幣數換成 OKX 可下單的 order size，再做 lot/min 量化。
        """
        inst_type = str(instrument.get("instType") or settings.instrument_type or "").upper()
        if inst_type not in {"SWAP", "FUTURES"}:
            return desired_size

        ct_val = self._safe_float(instrument.get("ctVal"), 0.0)
        if ct_val <= 0:
            return desired_size

        ct_mult = self._safe_float(instrument.get("ctMult"), 1.0)
        if ct_mult <= 0:
            ct_mult = 1.0

        contract_unit = ct_val * ct_mult
        if contract_unit <= 0:
            return desired_size

        return desired_size / contract_unit

    def preflight(self, inst_id: str, desired_size: float, desired_price: float | None) -> Dict[str, Any]:
        instrument = self.load_instrument(inst_id)
        if not instrument:
            return {"ok": False, "reason": "instrument_not_found"}

        lot_sz = instrument.get("lotSz", "1")
        min_sz = instrument.get("minSz", "1")
        tick_sz = instrument.get("tickSz", "0.1")

        raw_order_size = self._convert_base_size_to_order_size(instrument, desired_size)
        size = self.quantize_down(raw_order_size, lot_sz)
        min_sz_float = self._safe_float(min_sz, 1.0)
        if size < min_sz_float:
            size = min_sz_float

        price = self.quantize_down(desired_price, tick_sz) if desired_price is not None else None

        max_avail = None
        max_avail_reason = "not_checked"

        if settings.require_max_avail_check:
            max_row = self._max_avail_with_fallback(inst_id)
            max_avail = max_row.get("max_avail")
            max_avail_reason = max_row.get("reason", "unknown")

        if max_avail is not None and max_avail > 0:
            size = min(size, max_avail)
            size = self.quantize_down(size, lot_sz)

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
            "ct_val": instrument.get("ctVal"),
            "ct_mult": instrument.get("ctMult"),
            "raw_order_size": raw_order_size,
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
        available_usdt = float(account_summary.get("available_equity", account_summary.get("available", account_summary.get("equity", 0.0))) or 0.0)

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
                "raw_order_size": result.get("raw_order_size"),
                "ct_val": result.get("ct_val"),
                "ct_mult": result.get("ct_mult"),
                "max_avail": result.get("max_avail"),
                "max_avail_reason": result.get("max_avail_reason", "ok"),
            }

        return {
            "blocked": True,
            "reason": result.get("reason", "preflight_failed"),
            "max_avail_reason": result.get("max_avail_reason", "unknown"),
        }


PreflightService = LivePreflightService
