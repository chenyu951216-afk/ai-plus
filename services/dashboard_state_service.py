from typing import Dict, Any, List
from storage.state_store import StateStore


class DashboardStateService:
    def __init__(self) -> None:
        self.store = StateStore()

    def update(self, payload: Dict[str, Any]) -> None:
        self.store.save(payload)

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _format_watchlist(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for row in rows or []:
            entry = row.get("entry_decision", {}) or {}
            leverage = row.get("leverage_decision", {}) or {}
            tp_sl = row.get("tp_sl", {}) or {}
            preflight = row.get("preflight", {}) or {}
            formatted.append(
                {
                    "symbol": row.get("symbol", "-"),
                    "side": entry.get("side", "-"),
                    "confidence": self._to_float(entry.get("confidence", 0.0)),
                    "entry": self._to_float(row.get("last_price", 0.0)),
                    "tp": self._to_float(tp_sl.get("take_profit", 0.0)),
                    "sl": self._to_float(tp_sl.get("stop_loss", 0.0)),
                    "leverage": leverage.get("leverage", "-"),
                    "margin_pct": self._to_float(leverage.get("margin_pct", 0.0)),
                    "decision_reason": entry.get("decision_reason", ""),
                    "raw_action": entry.get("original_action", entry.get("action", "")),
                    "action": entry.get("action", ""),
                    "block_reason": entry.get("block_reason", ""),
                    "preflight_reason": preflight.get("reason", ""),
                    "trend_bias": row.get("trend_bias", ""),
                    "market_regime": row.get("market_regime", ""),
                    "template_summary": row.get("template_summary", ""),
                }
            )
        return formatted

    def _format_positions(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for row in rows or []:
            formatted.append(
                {
                    "symbol": row.get("instId", row.get("symbol", "-")),
                    "side": row.get("posSide", row.get("side", "-")),
                    "size": self._to_float(row.get("pos", row.get("size", 0.0))),
                    "entry_price": self._to_float(row.get("avgPx", row.get("entry_price", 0.0))),
                    "current_price": self._to_float(row.get("markPx", row.get("current_price", 0.0))),
                    "upl": self._to_float(row.get("upl", 0.0)),
                    "upl_ratio": self._to_float(row.get("uplRatio", row.get("upl_ratio", 0.0))),
                }
            )
        return formatted

    def _format_executed(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for row in rows or []:
            preflight = row.get("preflight", {}) or {}
            formatted.append(
                {
                    "symbol": row.get("symbol", "-"),
                    "execution_mode": row.get("execution_mode", "-"),
                    "final_size": self._to_float(row.get("final_size", row.get("desired_size", 0.0))),
                    "entry_price": self._to_float(row.get("entry_price", 0.0)),
                    "pos_side_used": row.get("pos_side_used", row.get("side", "net/none")),
                    "preflight": {
                        "reason": preflight.get("reason", "ok"),
                    },
                }
            )
        return formatted

    def _format_protective(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for row in rows or []:
            tp_sl = row.get("tp_sl", {}) or row
            formatted.append(
                {
                    "symbol": row.get("symbol", "-"),
                    "mode": row.get("mode", row.get("protection_profile", "-")),
                    "tp": self._to_float(tp_sl.get("take_profit", row.get("tp", 0.0))),
                    "sl": self._to_float(tp_sl.get("stop_loss", row.get("sl", 0.0))),
                    "size": self._to_float(row.get("size", row.get("final_size", 0.0))),
                }
            )
        return formatted

    def _format_roles(self, autonomy_audit: Dict[str, Any]) -> List[Dict[str, Any]]:
        roles = autonomy_audit.get("roles", []) if isinstance(autonomy_audit, dict) else []
        formatted: List[Dict[str, Any]] = []
        for row in roles or []:
            formatted.append(
                {
                    "role": row.get("role", "-"),
                    "owner": row.get("owner", "-"),
                    "status": row.get("status", "-"),
                }
            )
        return formatted

    def _normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        balance = payload.get("balance", {}) or {}
        autonomy_audit = payload.get("autonomy_audit", {}) or {}
        gpt_connection = payload.get("gpt_connection", {}) or {}
        scan_meta = payload.get("scan_meta", {}) or {}

        return {
            "balance": {
                "equity": self._to_float(balance.get("equity", balance.get("total_equity", 0.0))),
                "available": self._to_float(balance.get("available", balance.get("available_equity", 0.0))),
                "used_margin": self._to_float(balance.get("used_margin", 0.0)),
            },
            "autonomy_audit": {
                "autonomy_ratio": self._to_float(autonomy_audit.get("autonomy_ratio", 0.0)),
                "roles": self._format_roles(autonomy_audit),
            },
            "watchlist": self._format_watchlist(payload.get("watchlist", [])),
            "positions": self._format_positions(payload.get("positions", [])),
            "executed_orders": self._format_executed(payload.get("executed_orders", [])),
            "protective_orders": self._format_protective(payload.get("protective_orders", [])),
            "managed_positions": payload.get("managed_positions", []),
            "ai_recent_learning_plain": payload.get("ai_recent_learning_plain", "-"),
            "system_notes": payload.get("system_notes", []),
            "risk_guard": payload.get("risk_guard", {}),
            "trade_summary": payload.get("trade_summary", {}),
            "daily_gpt_review": payload.get("daily_gpt_review", {}),
            "adaptive_policy": payload.get("adaptive_policy", {}),
            "gpt_connection": gpt_connection,
            "scan_meta": scan_meta,
        }

    def read(self) -> Dict[str, Any]:
        payload = self.store.load()
        return self._normalize(payload if isinstance(payload, dict) else {})

    def get_state(self) -> Dict[str, Any]:
        return self.read()

    def build_state(self) -> Dict[str, Any]:
        return self.read()

    def snapshot(self) -> Dict[str, Any]:
        return self.read()
