import time
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

    def _algo_side(self, side: str) -> str:
        return "buy" if side == "short" else "sell"

    def _pos_side(self, side: str, account_pos_mode: str) -> str | None:
        return None if account_pos_mode in {"net", "net_mode"} and not settings.force_pos_side_in_net_mode else ("short" if side == "short" else "long")

    def register(self, execution_record: Dict[str, Any], account_pos_mode: str) -> Dict[str, Any]:
        symbol = execution_record["symbol"]
        side = execution_record["side"]
        size = float(execution_record.get("final_size", execution_record.get("desired_size", 1.0)) or 1.0)
        tp = execution_record.get("tp_sl", {}).get("take_profit_price")
        sl = execution_record.get("tp_sl", {}).get("stop_loss_price")
        algo_side = self._algo_side(side)
        pos_side = self._pos_side(side, account_pos_mode)

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
        algo_side = self._algo_side(side)
        pos_side = self._pos_side(side, account_pos_mode)
        result = self.client.safe_place_algo_tp_sl(
            inst_id=symbol,
            side=algo_side,
            pos_side=pos_side,
            tp_trigger_px=tp,
            sl_trigger_px=sl,
            size=size,
            margin_mode=settings.td_mode,
        ) if settings.enable_live_execution and settings.enable_protective_orders else {"code":"0","data":[{"algoId":f"paper-refresh-{symbol}"}]}
        record = {
            "symbol": symbol,
            "mode": "live" if settings.enable_live_execution else "paper",
            "action": "refresh",
            "reason": reason,
            "tp": tp,
            "sl": sl,
            "size": size,
            "result": result,
            "pos_side_used": pos_side,
            "timestamp": time.time(),
        }
        self.lifecycle.mark_refresh(symbol, side, reason)
        self.store.append(record)
        return record
