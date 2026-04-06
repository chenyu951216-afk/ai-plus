import time
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any
from clients.okx_client import OKXClient
from config.settings import settings
from storage.position_lifecycle_store import PositionLifecycleStore
from storage.protective_order_store import ProtectiveOrderStore


class ProtectiveOrderService:
    def __init__(self) -> None:
        self.client = OKXClient()
        self.store = ProtectiveOrderStore()
        self.lifecycle = PositionLifecycleStore()
        self.instrument_cache: dict[str, dict[str, Any]] = {}

    def _algo_side(self, side: str) -> str:
        return "buy" if side == "short" else "sell"

    def _pos_side(self, side: str, account_pos_mode: str) -> str | None:
        return None if account_pos_mode in {"net", "net_mode"} and not settings.force_pos_side_in_net_mode else ("short" if side == "short" else "long")

    def _normalize_size(self, value: Any) -> float:
        try:
            size = float(value or 0.0)
        except (TypeError, ValueError):
            size = 0.0
        return size if size > 0 else 0.0

    def _load_instrument(self, inst_id: str) -> dict[str, Any]:
        cached = self.instrument_cache.get(inst_id)
        if cached:
            return cached
        for row in self.client.safe_get_instruments():
            if str(row.get("instId", "")).upper() == str(inst_id).upper():
                self.instrument_cache[inst_id] = row
                return row
        return {}

    def _quantize_down(self, value: float | None, step: str | float | None) -> float | None:
        if value is None:
            return None
        try:
            v = Decimal(str(value))
            s = Decimal(str(step or "0"))
            if s <= 0:
                return float(v)
            return float((v / s).to_integral_value(rounding=ROUND_DOWN) * s)
        except Exception:
            return float(value)

    def _sanitize_tp_sl(self, symbol: str, side: str, entry_price: float, tp: Any, sl: Any) -> tuple[float | None, float | None]:
        try:
            tp_f = float(tp) if tp not in (None, "", 0, 0.0) else None
        except Exception:
            tp_f = None
        try:
            sl_f = float(sl) if sl not in (None, "", 0, 0.0) else None
        except Exception:
            sl_f = None

        inst = self._load_instrument(symbol) if settings.protect_price_guard_enabled else {}
        tick_sz = inst.get("tickSz", "0") if inst else "0"
        tp_f = self._quantize_down(tp_f, tick_sz)
        sl_f = self._quantize_down(sl_f, tick_sz)

        if entry_price <= 0:
            return tp_f, sl_f

        if side == "long":
            if tp_f is not None and tp_f <= entry_price:
                tp_f = None
            if sl_f is not None and sl_f >= entry_price:
                sl_f = None
        else:
            if tp_f is not None and tp_f >= entry_price:
                tp_f = None
            if sl_f is not None and sl_f <= entry_price:
                sl_f = None

        if tp_f is not None and tp_f <= 0:
            tp_f = None
        if sl_f is not None and sl_f <= 0:
            sl_f = None
        return tp_f, sl_f

    def register(self, execution_record: Dict[str, Any], account_pos_mode: str) -> Dict[str, Any]:
        symbol = execution_record["symbol"]
        side = execution_record["side"]

        if settings.skip_protective_if_entry_failed and not execution_record.get("order_success", True):
            result = {"code": "0", "msg": "skip_protective_entry_failed", "data": []}
            record = {
                "symbol": symbol,
                "mode": "live" if settings.enable_live_execution else "paper",
                "action": "register",
                "tp": None,
                "sl": None,
                "size": 0.0,
                "result": result,
                "pos_side_used": None,
                "timestamp": time.time(),
            }
            self.store.append(record)
            return record

        size = self._normalize_size(execution_record.get("final_size", execution_record.get("desired_size", 0.0)))
        entry_price = float(execution_record.get("entry_price", 0.0) or 0.0)
        raw_tp = execution_record.get("tp_sl", {}).get("take_profit_price")
        raw_sl = execution_record.get("tp_sl", {}).get("stop_loss_price")
        tp, sl = self._sanitize_tp_sl(symbol, side, entry_price, raw_tp, raw_sl)
        algo_side = self._algo_side(side)
        pos_side = self._pos_side(side, account_pos_mode)

        if size <= 0:
            result = {"code": "-1", "msg": "invalid_protective_order_size", "data": []}
        elif tp is None and sl is None:
            result = {"code": "0", "msg": "skip_protective_no_valid_trigger", "data": []}
        else:
            result = self.client.safe_place_algo_tp_sl(
                inst_id=symbol,
                side=algo_side,
                pos_side=pos_side,
                tp_trigger_px=tp,
                sl_trigger_px=sl,
                size=size,
                margin_mode=settings.td_mode,
            ) if settings.enable_live_execution and settings.enable_protective_orders else {"code":"0","data":[{"algoId":f"paper-protect-{symbol}"}]}

        record = {
            "symbol": symbol,
            "mode": "live" if settings.enable_live_execution else "paper",
            "action": "register",
            "tp": tp,
            "sl": sl,
            "size": size,
            "result": result,
            "pos_side_used": pos_side,
            "timestamp": time.time(),
        }
        self.lifecycle.mark_refresh(symbol, side, "register")
        self.store.append(record)
        return record

    def refresh(self, symbol: str, side: str, size: float, tp: float | None, sl: float | None, account_pos_mode: str, reason: str) -> Dict[str, Any]:
        normalized_size = self._normalize_size(size)
        entry_ref = float(tp or sl or 0.0)
        tp, sl = self._sanitize_tp_sl(symbol, side, entry_ref, tp, sl)
        algo_side = self._algo_side(side)
        pos_side = self._pos_side(side, account_pos_mode)

        if normalized_size <= 0:
            result = {"code": "-1", "msg": "invalid_protective_order_size", "data": []}
        elif tp is None and sl is None:
            result = {"code": "0", "msg": "skip_protective_no_valid_trigger", "data": []}
        else:
            result = self.client.safe_place_algo_tp_sl(
                inst_id=symbol,
                side=algo_side,
                pos_side=pos_side,
                tp_trigger_px=tp,
                sl_trigger_px=sl,
                size=normalized_size,
                margin_mode=settings.td_mode,
            ) if settings.enable_live_execution and settings.enable_protective_orders else {"code":"0","data":[{"algoId":f"paper-refresh-{symbol}"}]}

        record = {
            "symbol": symbol,
            "mode": "live" if settings.enable_live_execution else "paper",
            "action": "refresh",
            "reason": reason,
            "tp": tp,
            "sl": sl,
            "size": normalized_size,
            "result": result,
            "pos_side_used": pos_side,
            "timestamp": time.time(),
        }
        self.lifecycle.mark_refresh(symbol, side, reason)
        self.store.append(record)
        return record
