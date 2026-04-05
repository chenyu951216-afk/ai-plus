import logging
from typing import Any, Dict, List

from ai.adaptive_policy_store import AdaptivePolicyStore
from ai.autonomy_controller import AIAutonomyController
from ai.base_scorer import BaseScorer
from ai.ensemble_voter import EnsembleVoter
from ai.risk_guard_ai import RiskGuardAI
from analysis.breakout_analysis import BreakoutAnalyzer
from analysis.feature_builder import FeatureBuilder
from analysis.regime_detector import RegimeDetector
from analysis.technical_analysis import TechnicalAnalyzer
from analysis.trend_analysis import TrendAnalyzer
from config.settings import settings
from services.account_service import AccountService
from services.ai_review_judge_service import AIReviewJudgeService
from services.autonomy_audit_service import AutonomyAuditService
from services.daily_trade_digest_service import DailyTradeDigestService
from services.dashboard_state_service import DashboardStateService
from services.gpt_advisor_service import GPTAdvisorService
from services.market_pipeline_service import MarketPipelineService
from services.optimization_apply_service import OptimizationApplyService
from services.order_execution_service import OrderExecutionService
from services.position_manager_service import PositionManagerService
from services.position_sync_service import PositionSyncService
from services.preflight_service import PreflightService
from services.protective_order_service import ProtectiveOrderService
from storage.trade_store import TradeStore


class TradingRuntimeService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.pipeline = MarketPipelineService()
        self.account = AccountService()
        self.position_sync = PositionSyncService()
        self.preflight = PreflightService()
        self.order_exec = OrderExecutionService()
        self.protect = ProtectiveOrderService()
        self.position_manager = PositionManagerService()
        self.dashboard = DashboardStateService()
        self.trade_store = TradeStore()
        self.ai = AIAutonomyController()
        self.audit = AutonomyAuditService()
        self.base_scorer = BaseScorer()
        self.ensemble = EnsembleVoter()
        self.risk_guard = RiskGuardAI()
        self.technical = TechnicalAnalyzer()
        self.breakout = BreakoutAnalyzer()
        self.trend = TrendAnalyzer()
        self.regime = RegimeDetector()
        self.feature_builder = FeatureBuilder()
        self.policy_store = AdaptivePolicyStore()
        self.digest_service = DailyTradeDigestService()
        self.gpt = GPTAdvisorService()
        self.review_judge = AIReviewJudgeService()
        self.optimizer = OptimizationApplyService()

        self._scan_offset = 0
        self._cycle_count = 0

    def _run_daily_review_loop(self) -> Dict[str, Any]:
        if not settings.enable_daily_gpt_review:
            return {"enabled": False, "reason": "daily_review_disabled"}

        day = self.trade_store.latest_trading_day(settings.gpt_review_timezone) or self.digest_service.today_key()
        digest = self.digest_service.build_digest(day)

        if int(digest.get("trade_count", 0) or 0) < settings.daily_review_min_trades:
            return {
                "enabled": True,
                "reason": "not_enough_trades",
                "day": day,
                "trade_count": digest.get("trade_count", 0),
                "gpt_available": self.gpt.available(),
            }

        current_policy = self.policy_store.load()

        if str(current_policy.get("last_review_day", "")) == day:
            return {
                "enabled": True,
                "reason": "already_reviewed_today",
                "day": day,
                "summary": current_policy.get("last_review_summary", ""),
                "gpt_available": self.gpt.available(),
            }

        if not self.gpt.available():
            return {"enabled": True, "reason": "gpt_not_ready", "day": day, "gpt_available": False}

        review = self.gpt.review_daily_trades(digest, current_policy)
        judge = self.review_judge.evaluate(digest, review)
        consensus: Dict[str, Any] = {
            "initial_review": review,
            "judge": judge,
            "consensus_summary": str(review.get("summary", "")),
            "final_recommendations": list(judge.get("accepted_recommendations", [])),
            "discussion_rounds": [],
            "gpt_available": True,
        }

        working_review = review
        working_judge = judge
        for round_index in range(1, settings.gpt_deliberation_rounds + 1):
            if not working_judge.get("needs_more_discussion"):
                break

            discussion = self.gpt.discuss_disagreement(
                digest,
                working_review,
                {
                    "judge_verdict": working_judge.get("verdict"),
                    "objections": working_judge.get("objections", []),
                },
                current_policy,
                round_index,
            )
            consensus["discussion_rounds"].append(discussion)
            working_review = {
                **working_review,
                "recommendations": discussion.get(
                    "updated_recommendations",
                    working_review.get("recommendations", []),
                ),
                "summary": discussion.get(
                    "consensus_summary",
                    working_review.get("summary", ""),
                ),
            }
            working_judge = self.review_judge.evaluate(digest, working_review)
            consensus["consensus_summary"] = str(
                working_review.get("summary", consensus["consensus_summary"])
            )
            consensus["final_recommendations"] = list(
                working_judge.get("accepted_recommendations", [])
            )

            if not discussion.get("needs_more_discussion", False) and not working_judge.get("needs_more_discussion"):
                break

        adjustments = self.gpt.recommend_adjustments(digest, consensus, current_policy)
        saved_policy = self.optimizer.apply(day, adjustments, consensus)
        return {
            "enabled": True,
            "day": day,
            "digest": digest,
            "review": review,
            "judge": judge,
            "final_judge": working_judge,
            "consensus": consensus,
            "adjustments": adjustments,
            "saved_policy": saved_policy,
            "summary": saved_policy.get("last_review_summary", ""),
            "gpt_available": True,
        }

    def _bootstrap_softness(self, trade_summary: Dict[str, Any]) -> Dict[str, float]:
        total_closed = int(trade_summary.get("closed_count", trade_summary.get("total_count", 0)) or 0)
        if total_closed < 8:
            return {"entry_buffer": 0.10, "max_soft_entries": 2}
        if total_closed < 20:
            return {"entry_buffer": 0.06, "max_soft_entries": 1}
        return {"entry_buffer": 0.0, "max_soft_entries": 0}

    def _select_symbols_for_cycle(self, symbols: List[str]) -> List[str]:
        if not symbols:
            return []

        batch_size = int(getattr(settings, "scan_batch_size_per_cycle", 8) or 8)
        batch_size = max(3, min(batch_size, len(symbols)))

        start = self._scan_offset % len(symbols)
        end = start + batch_size
        if end <= len(symbols):
            selected = symbols[start:end]
        else:
            selected = symbols[start:] + symbols[: end - len(symbols)]

        self._scan_offset = (start + batch_size) % len(symbols)
        return selected

    def _build_watch_row(
        self,
        symbol: str,
        market_snapshot: Dict[str, Any],
        features: Dict[str, Any],
        entry_decision: Dict[str, Any],
        leverage_decision: Dict[str, Any],
        sizing_decision: Dict[str, Any],
        preflight: Dict[str, Any],
        decision_reason: str,
        block_reason: str,
    ) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "last_price": market_snapshot.get("last_price"),
            "quote_volume_24h": market_snapshot.get("quote_volume"),
            "change_24h": market_snapshot.get("change_24h", 0.0),
            "trend_bias": features.get("trend_bias"),
            "market_regime": features.get("market_regime"),
            "entry_decision": {
                **entry_decision,
                "decision_reason": decision_reason,
                "block_reason": block_reason,
            },
            "leverage_decision": leverage_decision,
            "sizing_decision": sizing_decision,
            "preflight": preflight,
            "tp_sl": {
                "take_profit": features.get("suggested_take_profit", 0.0),
                "stop_loss": features.get("suggested_stop_loss", 0.0),
            },
            "market_basis_categories": entry_decision.get("market_basis_categories", []),
            "template_summary": entry_decision.get("template_summary", ""),
            "scan_debug": {
                "feature_strength": float(features.get("feature_strength", 0.0) or 0.0),
                "pre_breakout_score": float(features.get("pre_breakout_score", 0.0) or 0.0),
                "ensemble_confidence": float(features.get("ensemble_confidence", 0.0) or 0.0),
            },
        }

    def _run_preflight(
        self,
        candidate: Dict[str, Any],
        account_summary: Dict[str, Any],
        pos_mode: str,
    ) -> Dict[str, Any]:
        if hasattr(self.preflight, "check"):
            return self.preflight.check(candidate, account_summary, pos_mode)

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
        desired_size = round(
            max(desired_notional / max(last_price, 1e-9), settings.lifecycle_min_position_size),
            8,
        )

        if hasattr(self.preflight, "preflight"):
            result = self.preflight.preflight(symbol, desired_size, last_price)
            if result.get("ok"):
                return {
                    "blocked": False,
                    "reason": "ok",
                    "final_size": result.get("final_size"),
                    "final_price": result.get("final_price"),
                    "max_avail": result.get("max_avail"),
                }
            return {
                "blocked": True,
                "reason": result.get("reason", "preflight_failed"),
            }

        return {"blocked": False, "reason": "preflight_unavailable"}

    def run_once(self) -> Dict[str, Any]:
        self._cycle_count += 1

        account_summary = self.account.summary()
        pos_mode = account_summary.get("pos_mode", "net")
        positions = self.position_sync.sync() if settings.enable_position_sync else []
        trade_summary = self.trade_store.summary(limit=50)
        risk_row = self.risk_guard.evaluate(account_summary)
        consecutive_losses = int(trade_summary.get("consecutive_losses", 0) or 0)

        if consecutive_losses >= settings.max_consecutive_losses_before_pause:
            risk_row = {**risk_row, "blocked": True, "reason": "max_consecutive_losses_reached"}

        autonomy = self.audit.run()
        symbols = self.pipeline.get_top_symbols()
        selected_symbols = self._select_symbols_for_cycle(symbols)

        try:
            scans = self.pipeline.scan(selected_symbols)
        except Exception as exc:
            self.logger.exception("scan batch failed: symbols=%s error=%s", selected_symbols, exc)
            scans = []

        bootstrap = self._bootstrap_softness(trade_summary)
        feature_map: Dict[str, Dict[str, Any]] = {}
        watchlist: List[Dict[str, Any]] = []
        execution_candidates: List[Dict[str, Any]] = []
        soft_entry_used = 0

        for scan in scans:
            symbol = scan["symbol"]
            df = scan["df"]
            market_snapshot = scan["market_snapshot"]

            tech = self.technical.analyze(df)
            breakout = self.breakout.analyze(df)
            trend = self.trend.analyze(df)
            regime = self.regime.detect(df, tech, breakout)
            base_out = self.base_scorer.score({**tech, **breakout, **trend, **regime})
            ensemble_out = self.ensemble.vote([base_out])

            features = self.feature_builder.build(
                symbol,
                market_snapshot,
                tech,
                breakout,
                trend,
                regime,
                ensemble_out,
            )
            feature_map[symbol] = features

            entry_decision = self.ai.decide_entry(features)
            leverage_decision = self.ai.decide_leverage(features)
            sizing_decision = self.ai.decide_sizing(features)

            confidence = float(entry_decision.get("confidence", 0.0) or 0.0)
            threshold = float(
                entry_decision.get("effective_threshold", settings.min_trade_confidence)
                or settings.min_trade_confidence
            )

            soft_enter = (
                entry_decision.get("action") != "enter"
                and bootstrap["entry_buffer"] > 0
                and confidence >= max(settings.adaptive_min_trade_confidence_floor, threshold - bootstrap["entry_buffer"])
                and soft_entry_used < bootstrap["max_soft_entries"]
            )

            candidate_action = "enter" if entry_decision.get("action") == "enter" or soft_enter else "wait"
            decision_reason = "ai_enter"
            if soft_enter:
                decision_reason = "bootstrap_soft_entry"
                soft_entry_used += 1

            candidate = {
                "symbol": symbol,
                "side": entry_decision.get("side", "long"),
                "entry_decision": {
                    **entry_decision,
                    "action": candidate_action,
                    "original_action": entry_decision.get("action"),
                    "decision_reason": decision_reason,
                },
                "leverage_decision": leverage_decision,
                "sizing_decision": sizing_decision,
                "features": features,
                "market_snapshot": market_snapshot,
            }

            preflight = self._run_preflight(candidate, account_summary, pos_mode)
            candidate["preflight"] = preflight

            block_reason = ""
            if candidate_action != "enter":
                block_reason = "ai_not_ready"
            elif preflight.get("blocked"):
                block_reason = preflight.get("reason", "preflight_blocked")

            watchlist.append(
                self._build_watch_row(
                    symbol=symbol,
                    market_snapshot=market_snapshot,
                    features=features,
                    entry_decision=candidate["entry_decision"],
                    leverage_decision=leverage_decision,
                    sizing_decision=sizing_decision,
                    preflight=preflight,
                    decision_reason=decision_reason,
                    block_reason=block_reason,
                )
            )

            self.logger.info(
                "[SCAN] cycle=%s symbol=%s action=%s raw_action=%s conf=%.4f thr=%.4f side=%s preflight=%s reason=%s",
                self._cycle_count,
                symbol,
                candidate_action,
                entry_decision.get("action"),
                confidence,
                threshold,
                candidate["side"],
                preflight.get("reason", "ok"),
                decision_reason,
            )

            if candidate_action == "enter" and not preflight.get("blocked"):
                execution_candidates.append(candidate)

        watchlist.sort(key=lambda x: float(x["entry_decision"].get("confidence", 0.0)), reverse=True)
        execution_candidates.sort(key=lambda x: float(x["entry_decision"].get("confidence", 0.0)), reverse=True)

        executed_orders: List[Dict[str, Any]] = []
        protective_orders: List[Dict[str, Any]] = []
        open_slots = max(settings.max_open_positions - len(positions), 0)
        allow_new_entries = min(open_slots, settings.max_live_entries_per_cycle)

        if not risk_row.get("blocked") and allow_new_entries > 0:
            for candidate in execution_candidates[:allow_new_entries]:
                execution = self.order_exec.execute(candidate, pos_mode, account_summary)
                executed_orders.append(execution)
                self.logger.info(
                    "[EXECUTE] cycle=%s symbol=%s mode=%s final_size=%s entry_price=%s preflight=%s",
                    self._cycle_count,
                    execution.get("symbol"),
                    execution.get("execution_mode"),
                    execution.get("final_size"),
                    execution.get("entry_price"),
                    candidate.get("preflight", {}).get("reason", "ok"),
                )
                if execution.get("execution_mode") != "blocked":
                    protective = self.protect.register(execution, pos_mode)
                    protective_orders.append(protective)
                    self.logger.info(
                        "[PROTECT] cycle=%s symbol=%s tp=%s sl=%s",
                        self._cycle_count,
                        protective.get("symbol"),
                        protective.get("tp"),
                        protective.get("sl"),
                    )
        elif risk_row.get("blocked"):
            self.logger.warning("new entries blocked by risk guard: %s", risk_row)

        managed_positions = self.position_manager.evaluate_positions(
            positions,
            feature_map,
            account_summary,
            pos_mode,
        )
        reflection = self.ai.reflect(self.trade_store.recent(limit=20))
        daily_review = self._run_daily_review_loop()
        current_policy = self.policy_store.load()

        payload = {
            "autonomy_audit": autonomy,
            "balance": account_summary,
            "risk_guard": risk_row,
            "trade_summary": trade_summary,
            "pnl_today": {"unrealized": round(sum(float(x.get("upl", 0.0)) for x in positions), 4)},
            "watchlist": watchlist[:10],
            "positions": positions[: settings.max_open_positions],
            "executed_orders": executed_orders,
            "protective_orders": protective_orders,
            "managed_positions": managed_positions,
            "ai_recent_learning_plain": reflection["plain_text"],
            "daily_gpt_review": daily_review,
            "adaptive_policy": current_policy,
            "market_basis_ready": True,
            "gpt_connection": {
                "available": self.gpt.available(),
                "model": settings.gpt_model,
                "daily_review_enabled": settings.enable_daily_gpt_review,
                "daily_review_reason": daily_review.get("reason", "ok"),
            },
            "scan_meta": {
                "cycle": self._cycle_count,
                "selected_symbols": selected_symbols,
                "selected_count": len(selected_symbols),
                "total_top_symbols": len(symbols),
                "bootstrap_entry_buffer": bootstrap["entry_buffer"],
                "bootstrap_max_soft_entries": bootstrap["max_soft_entries"],
            },
            "system_notes": [
                "初期進場條件已放寬，但只作用在交易候選，不直接放鬆學習保護。",
                "小樣本保護、異常日保護、連敗保護、GPT 建議緩變保護仍保留。",
                "已改為分批輪掃 top symbols，避免一次全掃造成 429。",
                f"ENABLE_LIVE_EXECUTION={settings.enable_live_execution}",
                f"OKX_IS_DEMO={settings.okx_is_demo}",
                f"KILL_SWITCH={settings.kill_switch}",
                f"posMode={pos_mode}",
                f"tdMode={settings.td_mode}",
                f"GPT_AVAILABLE={self.gpt.available()}",
                f"GPT_MODEL={settings.gpt_model}",
                f"BOOTSTRAP_ENTRY_BUFFER={bootstrap['entry_buffer']}",
                f"BOOTSTRAP_MAX_SOFT_ENTRIES={bootstrap['max_soft_entries']}",
                f"consecutive_losses={trade_summary.get('consecutive_losses', 0)}/{settings.max_consecutive_losses_before_pause}",
                f"SCAN_BATCH={len(selected_symbols)}/{len(symbols)}",
            ],
        }

        self.dashboard.update(payload)
        self.logger.info(
            "step40 done. cycle=%s scanned=%s/%s watch=%s positions=%s executed=%s autonomy=%.2f risk_blocked=%s daily_review=%s gpt=%s",
            self._cycle_count,
            len(selected_symbols),
            len(symbols),
            len(watchlist),
            len(positions),
            len(executed_orders),
            autonomy.get("autonomy_ratio", 0.0),
            risk_row.get("blocked"),
            daily_review.get("reason", daily_review.get("day", "ok")),
            self.gpt.available(),
        )
        return payload
