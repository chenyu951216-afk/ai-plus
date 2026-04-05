from typing import Any, Dict

from ai.adaptive_policy_store import AdaptivePolicyStore
from clients.okx_client import OKXClient
from config.settings import settings
from storage.order_store import OrderStore
from storage.position_lifecycle_store import PositionLifecycleStore
from storage.trade_store import TradeStore


class ExitExecutionService:
    def __init__(self) -> None:
        self.client = OKXClient()
        self.orders = OrderStore()
        self.trades = TradeStore()
        self.policy_store = AdaptivePolicyStore()
        self.lifecycle = PositionLifecycleStore()

    def _pos_side(self, side: str) -> str | None:
        return None if side in {"", "net"} and not settings.force_pos_side_in_net_mode else ("short" if side == "short" else "long")

    def _append_trade_record(self, position: Dict[str, Any], reason: str, size: float, management_action: str, review_area: str) -> None:
        policy = self.policy_store.load()
        upl_ratio = float(position.get("upl_ratio", position.get("uplRatio", 0.0)) or 0.0)
        lifecycle_state = position.get("lifecycle_state", {}) or {}
        trade_record: Dict[str, Any] = {
            "symbol": position["symbol"],
            "side": position.get("side"),
            "pnl": upl_ratio,
            "drawdown": float(position.get("max_drawdown", 0.0) or 0.0),
            "reason": reason,
            "review_area": review_area,
            "entry_confidence": float(position.get("entry_confidence", 0.0) or 0.0),
            "trend_bias": position.get("trend_bias"),
            "market_regime": position.get("market_regime", "unknown"),
            "pre_breakout_score": float(position.get("pre_breakout_score", 0.0) or 0.0),
            "size": size,
            "size_multiplier": float(position.get("size_multiplier", 1.0) or 1.0),
            "leverage": float(position.get("leverage", 0.0) or 0.0),
            "margin_pct": float(position.get("margin_pct", 0.0) or 0.0),
            "exit_style": policy.get("exit_style", "balanced"),
            "protection_profile": policy.get("protection_profile", "balanced"),
            "position_management_profile": policy.get("position_management_profile", "balanced"),
            "management_action": management_action,
            "protection_state": position.get("protection_state", policy.get("protection_profile", "balanced")),
            "lifecycle_stage": position.get("lifecycle_stage", "none"),
            "lifecycle_snapshot": lifecycle_state,
        }
        self.trades.append(trade_record)

    def close_position(self, position: Dict[str, Any], reason: str) -> Dict[str, Any]:
        side = "buy" if position["side"] == "short" else "sell"
        pos_side = self._pos_side(position.get("side", ""))
        size = max(float(position.get("size", 0.0) or 0.0), settings.lifecycle_min_position_size)
        result = (
            self.client.safe_place_order(
                inst_id=position["symbol"],
                side=side,
                pos_side=pos_side,
                size=size,
                order_type="market",
                price=None,
                reduce_only=True,
                margin_mode=settings.td_mode,
            )
            if settings.enable_live_execution
            else {"code": "0", "data": [{"ordId": f"paper-close-{position['symbol']}"}]}
        )
        self.orders.append({"symbol": position["symbol"], "exit_reason": reason, "close_result": result})
        self._append_trade_record(position, reason, size, "full_exit", "exit")
        self.lifecycle.clear(position["symbol"], position.get("side", ""))
        return {"symbol": position["symbol"], "reason": reason, "execution_mode": "live" if settings.enable_live_execution else "paper", "order_result": result}

    def partial_close_position(self, position: Dict[str, Any], reason: str, fraction: float) -> Dict[str, Any]:
        fraction = max(0.05, min(0.95, float(fraction or settings.lifecycle_reduce_fraction)))
        side = "buy" if position["side"] == "short" else "sell"
        pos_side = self._pos_side(position.get("side", ""))
        original_size = max(float(position.get("size", 0.0) or 0.0), settings.lifecycle_min_position_size)
        close_size = round(max(settings.lifecycle_min_position_size, original_size * fraction), 8)
        result = (
            self.client.safe_place_order(
                inst_id=position["symbol"],
                side=side,
                pos_side=pos_side,
                size=close_size,
                order_type="market",
                price=None,
                reduce_only=True,
                margin_mode=settings.td_mode,
            )
            if settings.enable_live_execution
            else {"code": "0", "data": [{"ordId": f"paper-partial-{position['symbol']}"}]}
        )
        self.orders.append({"symbol": position["symbol"], "exit_reason": reason, "partial_close_result": result, "fraction": fraction})
        self._append_trade_record(position, reason, close_size, position.get("management_action", "partial_exit"), "position_management")
        state = self.lifecycle.get(position["symbol"], position.get("side", ""))
        updates = {
            "partial_exit_count": int(state.get("partial_exit_count", 0) or 0) + 1,
            "last_action": position.get("management_action", "partial_exit"),
            "last_reason": reason,
        }
        stage = str(position.get("lifecycle_stage", ""))
        if stage == "tp1":
            updates["tp1_done"] = True
        elif stage == "tp2":
            updates["tp2_done"] = True
        self.lifecycle.update(position["symbol"], position.get("side", ""), updates)
        return {
            "symbol": position["symbol"],
            "reason": reason,
            "fraction": fraction,
            "execution_mode": "live" if settings.enable_live_execution else "paper",
            "order_result": result,
        }
