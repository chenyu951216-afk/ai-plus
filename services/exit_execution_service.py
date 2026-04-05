from __future__ import annotations

import time
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

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _extract_order_id(self, result: Dict[str, Any]) -> str:
        rows = result.get("data", []) if isinstance(result, dict) else []
        if rows and isinstance(rows[0], dict):
            return str(rows[0].get("ordId", "") or "")
        return ""

    def _estimate_realized_pnl_fallback(self, position: Dict[str, Any], closed_size: float) -> Dict[str, Any]:
        original_size = max(self._safe_float(position.get("size", 0.0), 0.0), settings.lifecycle_min_position_size)
        close_fraction = min(max(closed_size / max(original_size, 1e-9), 0.0), 1.0)
        upl_amount = self._safe_float(position.get("upl", 0.0), 0.0)
        upl_ratio = self._safe_float(position.get("upl_ratio", position.get("uplRatio", 0.0)), 0.0)
        entry_price = self._safe_float(position.get("entry_price", 0.0), 0.0)
        mark_price = self._safe_float(position.get("current_price", entry_price), entry_price)
        realized_amount = upl_amount * close_fraction
        return {
            "realized_pnl": realized_amount,
            "realized_pnl_source": "position_upl_fallback",
            "pnl_ratio": upl_ratio * close_fraction,
            "close_price": mark_price,
            "filled_size": closed_size,
            "fill_fee": 0.0,
            "fill_fee_ccy": "",
            "entry_price": entry_price,
            "close_fraction": close_fraction,
        }

    def _fetch_realized_close_snapshot(self, position: Dict[str, Any], result: Dict[str, Any], requested_size: float) -> Dict[str, Any]:
        ord_id = self._extract_order_id(result)
        inst_id = str(position.get("symbol", "") or "")
        if not settings.enable_live_execution or not ord_id or not inst_id:
            return self._estimate_realized_pnl_fallback(position, requested_size)

        detail_row: Dict[str, Any] = {}
        for _ in range(4):
            try:
                payload = self.client._request(
                    "GET",
                    "/api/v5/trade/order",
                    params={"instId": inst_id, "ordId": ord_id},
                    private=True,
                )
                rows = payload.get("data", []) if isinstance(payload, dict) else []
                if rows and isinstance(rows[0], dict):
                    detail_row = rows[0]
                    if detail_row.get("state") in {"filled", "partially_filled"} or detail_row.get("accFillSz") not in (None, "", "0"):
                        break
            except Exception:
                detail_row = {}
            time.sleep(0.35)

        if detail_row:
            fill_pnl = self._safe_float(detail_row.get("fillPnl"), 0.0)
            fill_fee = self._safe_float(detail_row.get("fillFee"), 0.0)
            close_price = self._safe_float(detail_row.get("avgPx") or detail_row.get("fillPx") or detail_row.get("px"), 0.0)
            filled_size = self._safe_float(detail_row.get("accFillSz") or detail_row.get("fillSz"), requested_size)
            entry_price = self._safe_float(position.get("entry_price", 0.0), 0.0)
            realized_amount = fill_pnl + fill_fee
            if fill_pnl != 0.0 or fill_fee != 0.0 or close_price > 0.0:
                basis = max(entry_price * max(filled_size, 0.0), 1e-9)
                pnl_ratio = realized_amount / basis if basis > 0 else 0.0
                return {
                    "realized_pnl": realized_amount,
                    "realized_pnl_source": "okx_order_details",
                    "pnl_ratio": pnl_ratio,
                    "close_price": close_price,
                    "filled_size": filled_size,
                    "fill_fee": fill_fee,
                    "fill_fee_ccy": str(detail_row.get("fillFeeCcy") or detail_row.get("feeCcy") or ""),
                    "entry_price": entry_price,
                    "close_fraction": min(max(filled_size / max(self._safe_float(position.get('size', 0.0), 0.0), 1e-9), 0.0), 1.0),
                    "ord_id": ord_id,
                    "trade_id": str(detail_row.get("tradeId", "") or ""),
                }

        return self._estimate_realized_pnl_fallback(position, requested_size)

    def _append_trade_record(self, position: Dict[str, Any], reason: str, size: float, management_action: str, review_area: str, execution_snapshot: Dict[str, Any]) -> None:
        policy = self.policy_store.load()
        lifecycle_state = position.get("lifecycle_state", {}) or {}
        realized_pnl = self._safe_float(execution_snapshot.get("realized_pnl"), 0.0)
        pnl_ratio = self._safe_float(execution_snapshot.get("pnl_ratio"), self._safe_float(position.get("upl_ratio", position.get("uplRatio", 0.0)), 0.0))
        trade_record: Dict[str, Any] = {
            "symbol": position["symbol"],
            "side": position.get("side"),
            "pnl": realized_pnl,
            "pnl_amount": realized_pnl,
            "pnl_ratio": pnl_ratio,
            "drawdown": float(position.get("max_drawdown", 0.0) or 0.0),
            "reason": reason,
            "review_area": review_area,
            "entry_confidence": float(position.get("entry_confidence", 0.0) or 0.0),
            "trend_bias": position.get("trend_bias"),
            "market_regime": position.get("market_regime", "unknown"),
            "pre_breakout_score": float(position.get("pre_breakout_score", 0.0) or 0.0),
            "size": size,
            "filled_size": self._safe_float(execution_snapshot.get("filled_size"), size),
            "size_multiplier": float(position.get("size_multiplier", 1.0) or 1.0),
            "leverage": float(position.get("leverage", 0.0) or 0.0),
            "margin_pct": float(position.get("margin_pct", 0.0) or 0.0),
            "entry_price": self._safe_float(execution_snapshot.get("entry_price"), self._safe_float(position.get("entry_price", 0.0), 0.0)),
            "close_price": self._safe_float(execution_snapshot.get("close_price"), self._safe_float(position.get("current_price", 0.0), 0.0)),
            "fill_fee": self._safe_float(execution_snapshot.get("fill_fee"), 0.0),
            "fill_fee_ccy": str(execution_snapshot.get("fill_fee_ccy", "") or ""),
            "realized_pnl_source": str(execution_snapshot.get("realized_pnl_source", "unknown") or "unknown"),
            "exit_style": policy.get("exit_style", "balanced"),
            "protection_profile": policy.get("protection_profile", "balanced"),
            "position_management_profile": policy.get("position_management_profile", "balanced"),
            "management_action": management_action,
            "protection_state": position.get("protection_state", policy.get("protection_profile", "balanced")),
            "lifecycle_stage": position.get("lifecycle_stage", "none"),
            "lifecycle_snapshot": lifecycle_state,
            "close_fraction": self._safe_float(execution_snapshot.get("close_fraction"), 1.0),
            "ord_id": str(execution_snapshot.get("ord_id", "") or ""),
            "trade_id": str(execution_snapshot.get("trade_id", "") or ""),
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
        execution_snapshot = self._fetch_realized_close_snapshot(position, result, size)
        self.orders.append({
            "symbol": position["symbol"],
            "exit_reason": reason,
            "close_result": result,
            "realized_pnl": execution_snapshot.get("realized_pnl", 0.0),
            "close_price": execution_snapshot.get("close_price", 0.0),
            "fill_fee": execution_snapshot.get("fill_fee", 0.0),
        })
        self._append_trade_record(position, reason, size, "full_exit", "exit", execution_snapshot)
        self.lifecycle.clear(position["symbol"], position.get("side", ""))
        return {
            "symbol": position["symbol"],
            "reason": reason,
            "execution_mode": "live" if settings.enable_live_execution else "paper",
            "order_result": result,
            "realized_pnl": execution_snapshot.get("realized_pnl", 0.0),
            "close_price": execution_snapshot.get("close_price", 0.0),
            "realized_pnl_source": execution_snapshot.get("realized_pnl_source", "unknown"),
        }

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
        execution_snapshot = self._fetch_realized_close_snapshot(position, result, close_size)
        self.orders.append({
            "symbol": position["symbol"],
            "exit_reason": reason,
            "partial_close_result": result,
            "fraction": fraction,
            "realized_pnl": execution_snapshot.get("realized_pnl", 0.0),
            "close_price": execution_snapshot.get("close_price", 0.0),
            "fill_fee": execution_snapshot.get("fill_fee", 0.0),
        })
        self._append_trade_record(position, reason, close_size, position.get("management_action", "partial_exit"), "position_management", execution_snapshot)
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
            "realized_pnl": execution_snapshot.get("realized_pnl", 0.0),
            "close_price": execution_snapshot.get("close_price", 0.0),
            "realized_pnl_source": execution_snapshot.get("realized_pnl_source", "unknown"),
        }
