import time
from typing import Dict, Any, List
from ai.autonomy_controller import AIAutonomyController
from ai.risk_guard_ai import RiskGuardAI
from ai.tp_sl_advisor import TPSLAdvisor
from config.settings import settings
from services.exit_execution_service import ExitExecutionService
from services.order_execution_service import OrderExecutionService
from services.protective_order_service import ProtectiveOrderService
from storage.position_lifecycle_store import PositionLifecycleStore


class PositionManagerService:
    def __init__(self) -> None:
        self.ai = AIAutonomyController()
        self.risk = RiskGuardAI()
        self.exit = ExitExecutionService()
        self.order_exec = OrderExecutionService()
        self.protect = ProtectiveOrderService()
        self.tp_sl = TPSLAdvisor()
        self.lifecycle = PositionLifecycleStore()

    def _should_refresh(self, symbol: str, side: str, requested: bool, reason: str) -> bool:
        if not requested:
            return False
        state = self.lifecycle.get(symbol, side)
        last_ts = float(state.get("last_refresh_ts", 0.0) or 0.0)
        if reason in {"scale_in", "tp_stage_1_lock_in", "tp_stage_2_lock_in", "protection_refresh"}:
            return True
        return (time.time() - last_ts) >= settings.lifecycle_protection_refresh_cooldown_sec

    def _build_tp_sl(self, feat: Dict[str, Any], side: str, confidence: float) -> Dict[str, Any]:
        return self.tp_sl.suggest(feat, side, confidence)

    def evaluate_positions(self, positions: List[Dict[str, Any]], feature_map: Dict[str, Dict[str, Any]], account_summary: Dict[str, Any], pos_mode: str) -> List[Dict[str, Any]]:
        rows = []
        risk = self.risk.evaluate(account_summary)
        for pos in positions:
            feat = feature_map.get(pos["symbol"], {})
            lifecycle_state = self.lifecycle.get(pos["symbol"], pos.get("side", ""))
            pos_ctx = {**pos, "lifecycle_state": lifecycle_state}
            protection = self.ai.decide_protection(pos_ctx, feat)
            sizing = self.ai.decide_sizing({"ensemble_confidence": feat.get("ensemble_confidence", 0.5), **feat})
            management = self.ai.decide_position_management(pos_ctx, feat, protection)
            exit_row = None
            mgmt_row = None
            protect_row = None
            exit_decision = self.ai.decide_exit(pos_ctx, feat)
            confidence = float(feat.get("ensemble_confidence", 0.0) or 0.0)

            if exit_decision.get("action") == "exit":
                exit_row = self.exit.close_position({**pos_ctx, **feat, "protection_state": protection.get("protection_profile", "balanced")}, exit_decision.get("reason", "ai_exit"))
            elif exit_decision.get("action") == "partial_exit":
                exit_row = self.exit.partial_close_position({**pos_ctx, **feat, "protection_state": protection.get("protection_profile", "balanced"), "management_action": "partial_exit", "lifecycle_stage": "exit_trim"}, exit_decision.get("reason", "ai_partial_exit"), settings.lifecycle_reduce_fraction)
            elif settings.enable_position_lifecycle and management.get("action") in {"scale_in", "reduce_risk", "partial_take_profit"} and not risk.get("blocked"):
                action = management.get("action")
                fraction = float(management.get("fraction", 0.0) or 0.0)
                if action == "scale_in":
                    mgmt_row = self.order_exec.manage_position(pos["symbol"], pos.get("side", "long"), pos_mode, float(pos.get("size", 0.0) or 0.0), fraction, "scale_in", feat)
                else:
                    mgmt_row = self.exit.partial_close_position({**pos_ctx, **feat, "protection_state": protection.get("protection_profile", "balanced"), "management_action": action, "lifecycle_stage": management.get("lifecycle_stage", action)}, management.get("reason", action), fraction)
                if self._should_refresh(pos["symbol"], pos.get("side", "long"), protection.get("refresh_protection", False), management.get("reason", action)):
                    tp_sl = self._build_tp_sl(feat, pos.get("side", "long"), confidence)
                    protect_row = self.protect.refresh(
                        symbol=pos["symbol"],
                        side=pos.get("side", "long"),
                        size=max(float(pos.get("size", 0.0) or 0.0), settings.lifecycle_min_position_size),
                        tp=tp_sl.get("take_profit_price"),
                        sl=tp_sl.get("stop_loss_price"),
                        account_pos_mode=pos_mode,
                        reason=management.get("reason", action),
                    )
            elif self._should_refresh(pos["symbol"], pos.get("side", "long"), protection.get("refresh_protection", False), "protection_refresh"):
                tp_sl = self._build_tp_sl(feat, pos.get("side", "long"), confidence)
                protect_row = self.protect.refresh(
                    symbol=pos["symbol"],
                    side=pos.get("side", "long"),
                    size=max(float(pos.get("size", 0.0) or 0.0), settings.lifecycle_min_position_size),
                    tp=tp_sl.get("take_profit_price"),
                    sl=tp_sl.get("stop_loss_price"),
                    account_pos_mode=pos_mode,
                    reason="protection_refresh",
                )
            rows.append({
                "symbol": pos["symbol"],
                "lifecycle_state": lifecycle_state,
                "protection": protection,
                "sizing": sizing,
                "risk_guard": risk,
                "management": management,
                "management_result": mgmt_row,
                "protection_result": protect_row,
                "exit": exit_row,
            })
        return rows
