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

    def _is_okx_success(self, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        if str(payload.get("code", "-1")) not in {"0", "", "None"}:
            return False
        rows = payload.get("data", []) or []
        if not rows:
            return True
        for row in rows:
            if str(row.get("sCode", "0")) not in {"0", "", "None"}:
                return False
        return True

    def execute(self, candidate: Dict[str, Any], pos_mode: str, account_summary: Dict[str, Any]) -> Dict[str, Any]:
        preflight = candidate.get("preflight", {})
        if preflight.get("blocked"):
            return {
                "symbol": candidate["symbol"],
                "side": candidate["side"],
                "execution_mode": "blocked",
                "order_success": False,
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

        preflight_final_size = preflight.get("final_size")
        if preflight_final_size is None:
            preflight_final_size = preflight.get("adjusted_size")
        final_size = float(preflight_final_size if preflight_final_size not in (None, "", 0, 0.0) else desired_size)

        preflight_entry_price = preflight.get("entry_price")
        if preflight_entry_price is None:
            preflight_entry_price = preflight.get("price")
        entry_price = preflight_entry_price if preflight_entry_price not in (None, "") else last_price

        pos_side = self._position_pos_side(pos_mode, candidate["side"])
        order_side = "buy" if candidate["side"] == "long" else "sell"

        leverage_result = (
            self.client.safe_set_leverage(
                inst_id=candidate["symbol"],
                leverage=leverage,
                margin_mode=settings.td_mode,
                pos_side=pos_side,
            )
            if settings.enable_live_execution and settings.set_leverage_before_entry
            else {"code": "0", "data": [{"msg": "leverage_setup_skipped"}]}
        )
        leverage_success = self._is_okx_success(leverage_result)

        result = (
            self.client.safe_place_order(
                inst_id=candidate["symbol"],
                side=order_side,
                pos_side=pos_side,
                size=final_size,
                order_type="market",
                price=None,
                reduce_only=False,
                margin_mode=settings.td_mode,
            )
            if settings.enable_live_execution
            else {"code": "0", "data": [{"ordId": f"paper-{candidate['symbol']}"}]}
        )
        order_success = self._is_okx_success(result)

        tp_sl = self.tp_sl.suggest(
            candidate.get("features", {}),
            candidate["side"],
            float(candidate.get("entry_decision", {}).get("confidence", 0.0) or 0.0),
        )
        execution_mode = "paper" if not settings.enable_live_execution else ("live" if order_success else "failed")
        execution = {
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "execution_mode": execution_mode,
            "order_success": order_success,
            "order_result": result,
            "leverage_result": leverage_result,
            "leverage_success": leverage_success,
            "desired_size": desired_size,
            "final_size": final_size,
            "entry_price": entry_price,
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
            "reason": "order_placed" if order_success else "order_rejected",
        }
        if order_success:
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
        order_success = self._is_okx_success(result)
        state = self.lifecycle.get(symbol, side)
        updates = {"last_action": action, "last_reason": action}
        if action == "scale_in" and order_success:
            updates["scale_in_count"] = int(state.get("scale_in_count", 0) or 0) + 1
        record = {
            "symbol": symbol,
            "side": side,
            "execution_mode": "live" if settings.enable_live_execution else "paper",
            "order_success": order_success,
            "management_action": action,
            "managed_size": target_size,
            "fraction": fraction,
            "order_result": result,
            "trend_bias": features.get("trend_bias"),
            "market_regime": features.get("market_regime", "unknown"),
            "pre_breakout_score": float(features.get("pre_breakout_score", 0.0) or 0.0),
            "review_area": "position_management",
        }
        if order_success:
            self.lifecycle.update(symbol, side, updates)
        self.orders.append(record)
        return record
