from typing import Any, Dict

from ai.adaptive_policy_store import AdaptivePolicyStore
from ai.tp_sl_advisor import TPSLAdvisor
from clients.okx_client import OKXClient
from config.settings import settings
from storage.order_store import OrderStore
from storage.position_lifecycle_store import PositionLifecycleStore


class OrderExecutionService:
    def __init__(self) -> None:
        self.client = OKXClient()
        self.orders = OrderStore()
        self.policy_store = AdaptivePolicyStore()
        self.tp_sl = TPSLAdvisor()
        self.lifecycle = PositionLifecycleStore()

    def _position_pos_side(self, pos_mode: str, side: str) -> str | None:
        return None if pos_mode == "net" and not settings.force_pos_side_in_net_mode else side

    def _estimate_size(self, last_price: float, available_usdt: float, leverage: int, margin_pct: float, size_multiplier: float) -> float:
        desired_margin = max(available_usdt * margin_pct * size_multiplier, 1.0)
        desired_notional = desired_margin * max(leverage, 1)
        return round(max(desired_notional / max(last_price, 1e-9), settings.lifecycle_min_position_size), 8)

    def execute(self, candidate: Dict[str, Any], pos_mode: str, account_summary: Dict[str, Any]) -> Dict[str, Any]:
        preflight = candidate.get("preflight", {})
        if preflight.get("blocked"):
            return {
                "symbol": candidate["symbol"],
                "side": candidate["side"],
                "execution_mode": "blocked",
                "reason": preflight.get("reason", "preflight_blocked"),
                "preflight": preflight,
            }

        leverage_decision = candidate.get("leverage_decision", {})
        sizing_decision = candidate.get("sizing_decision", {})
        policy = self.policy_store.load()
        leverage = int(leverage_decision.get("leverage", settings.default_leverage_min))
        margin_pct = float(leverage_decision.get("margin_pct", settings.default_margin_pct_min))
        size_multiplier = float(sizing_decision.get("size_multiplier", 1.0) or 1.0)
        last_price = float(candidate.get("market_snapshot", {}).get("last_price", 0.0) or 0.0)
        available_usdt = float(account_summary.get("available_equity", account_summary.get("equity", 0.0)) or 0.0)
        desired_size = self._estimate_size(last_price, available_usdt, leverage, margin_pct, size_multiplier)
        pos_side = self._position_pos_side(pos_mode, candidate["side"])
        order_side = "buy" if candidate["side"] == "long" else "sell"
        result = (
            self.client.safe_place_order(
                inst_id=candidate["symbol"],
                side=order_side,
                pos_side=pos_side,
                size=desired_size,
                order_type="market",
                price=None,
                reduce_only=False,
                margin_mode=settings.td_mode,
            )
            if settings.enable_live_execution
            else {"code": "0", "data": [{"ordId": f"paper-{candidate['symbol']}"}]}
        )
        tp_sl = self.tp_sl.suggest(candidate.get("features", {}), candidate["side"], float(candidate.get("entry_decision", {}).get("confidence", 0.0) or 0.0))
        execution = {
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "execution_mode": "live" if settings.enable_live_execution else "paper",
            "order_result": result,
            "desired_size": desired_size,
            "final_size": desired_size,
            "size_multiplier": size_multiplier,
            "leverage": leverage,
            "margin_pct": margin_pct,
            "entry_confidence": float(candidate.get("entry_decision", {}).get("confidence", 0.0) or 0.0),
            "trend_bias": candidate.get("features", {}).get("trend_bias"),
            "market_regime": candidate.get("features", {}).get("market_regime", "unknown"),
            "pre_breakout_score": float(candidate.get("features", {}).get("pre_breakout_score", 0.0) or 0.0),
            "review_area": "entry",
            "exit_style": policy.get("exit_style", "balanced"),
            "protection_profile": policy.get("protection_profile", "balanced"),
            "position_management_profile": policy.get("position_management_profile", "balanced"),
            "management_action": "entry",
            "protection_state": policy.get("protection_profile", "balanced"),
            "tp_sl": tp_sl,
            "preflight": preflight,
        }
        self.lifecycle.update(candidate["symbol"], candidate["side"], {
            "scale_in_count": 0,
            "partial_exit_count": 0,
            "tp1_done": False,
            "tp2_done": False,
            "last_action": "entry",
            "last_reason": "new_position",
        })
        self.orders.append(execution)
        return execution

    def manage_position(self, symbol: str, side: str, pos_mode: str, current_size: float, fraction: float, action: str, features: Dict[str, Any]) -> Dict[str, Any]:
        fraction = max(0.0, float(fraction or 0.0))
        target_size = round(max(settings.lifecycle_min_position_size, current_size * fraction), 8)
        if action == "scale_in":
            order_side = "buy" if side == "long" else "sell"
            reduce_only = False
        else:
            order_side = "sell" if side == "long" else "buy"
            reduce_only = True
        pos_side = self._position_pos_side(pos_mode, side)
        result = (
            self.client.safe_place_order(
                inst_id=symbol,
                side=order_side,
                pos_side=pos_side,
                size=target_size,
                order_type="market",
                price=None,
                reduce_only=reduce_only,
                margin_mode=settings.td_mode,
            )
            if settings.enable_live_execution
            else {"code": "0", "data": [{"ordId": f"paper-manage-{symbol}-{action}"}]}
        )
        state = self.lifecycle.get(symbol, side)
        updates = {"last_action": action, "last_reason": action}
        if action == "scale_in":
            updates["scale_in_count"] = int(state.get("scale_in_count", 0) or 0) + 1
        record = {
            "symbol": symbol,
            "side": side,
            "execution_mode": "live" if settings.enable_live_execution else "paper",
            "management_action": action,
            "managed_size": target_size,
            "fraction": fraction,
            "order_result": result,
            "trend_bias": features.get("trend_bias"),
            "market_regime": features.get("market_regime", "unknown"),
            "pre_breakout_score": float(features.get("pre_breakout_score", 0.0) or 0.0),
            "review_area": "position_management",
        }
        self.lifecycle.update(symbol, side, updates)
        self.orders.append(record)
        return record
