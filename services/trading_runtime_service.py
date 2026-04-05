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

    def _run_daily_review_loop(self) -> Dict[str, Any]:
        if not settings.enable_daily_gpt_review:
            return {"enabled": False, "reason": "daily_review_disabled"}
        day = self.trade_store.latest_trading_day(settings.gpt_review_timezone) or self.digest_service.today_key()
        digest = self.digest_service.build_digest(day)
        if int(digest.get("trade_count", 0) or 0) < settings.daily_review_min_trades:
            return {"enabled": True, "reason": "not_enough_trades", "day": day, "trade_count": digest.get("trade_count", 0)}

        current_policy = self.policy_store.load()
        if str(current_policy.get("last_review_day", "")) == day:
            return {
                "enabled": True,
                "reason": "already_reviewed_today",
                "day": day,
                "summary": current_policy.get("last_review_summary", ""),
            }
        if not self.gpt.available():
            return {"enabled": True, "reason": "gpt_not_ready", "day": day}

        review = self.gpt.review_daily_trades(digest, current_policy)
        judge = self.review_judge.evaluate(digest, review)
        consensus: Dict[str, Any] = {
            "initial_review": review,
            "judge": judge,
            "consensus_summary": str(review.get("summary", "")),
            "final_recommendations": list(judge.get("accepted_recommendations", [])),
            "discussion_rounds": [],
        }

        working_review = review
        working_judge = judge
        for round_index in range(1, settings.gpt_deliberation_rounds + 1):
            if not working_judge.get("needs_more_discussion"):
                break
            discussion = self.gpt.discuss_disagreement(digest, working_review, {
                "judge_verdict": working_judge.get("verdict"),
                "objections": working_judge.get("objections", []),
            }, current_policy, round_index)
            consensus["discussion_rounds"].append(discussion)
            working_review = {
                **working_review,
                "recommendations": discussion.get("updated_recommendations", working_review.get("recommendations", [])),
                "summary": discussion.get("consensus_summary", working_review.get("summary", "")),
            }
            working_judge = self.review_judge.evaluate(digest, working_review)
            consensus["consensus_summary"] = str(working_review.get("summary", consensus["consensus_summary"]))
            consensus["final_recommendations"] = list(working_judge.get("accepted_recommendations", []))
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
        }

    def run_once(self) -> Dict[str, Any]:
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
        scans = self.pipeline.scan(symbols)

        feature_map: Dict[str, Dict[str, Any]] = {}
        watchlist: List[Dict[str, Any]] = []
        execution_candidates: List[Dict[str, Any]] = []
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
            features = self.feature_builder.build(symbol, market_snapshot, tech, breakout, trend, regime, ensemble_out)
            feature_map[symbol] = features
            entry_decision = self.ai.decide_entry(features)
            if float(entry_decision.get("confidence", 0.0)) >= settings.min_watch_confidence:
                watchlist.append({
                    "symbol": symbol,
                    "last_price": market_snapshot.get("last_price"),
                    "quote_volume_24h": market_snapshot.get("quote_volume"),
                    "change_24h": market_snapshot.get("change_24h", 0.0),
                    "trend_bias": features.get("trend_bias"),
                    "market_regime": features.get("market_regime"),
                    "entry_decision": entry_decision,
                    "market_basis_categories": entry_decision.get("market_basis_categories", []),
                    "template_summary": entry_decision.get("template_summary", ""),
                })
            if entry_decision.get("action") == "enter":
                leverage_decision = self.ai.decide_leverage(features)
                sizing_decision = self.ai.decide_sizing(features)
                candidate = {
                    "symbol": symbol,
                    "side": entry_decision.get("side", "long"),
                    "entry_decision": entry_decision,
                    "leverage_decision": leverage_decision,
                    "sizing_decision": sizing_decision,
                    "features": features,
                    "market_snapshot": market_snapshot,
                }
                candidate["preflight"] = self.preflight.check(candidate, account_summary, pos_mode)
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
                if execution.get("execution_mode") != "blocked":
                    protective_orders.append(self.protect.register(execution, pos_mode))
        elif risk_row.get("blocked"):
            self.logger.warning("new entries blocked by risk guard: %s", risk_row)

        managed_positions = self.position_manager.evaluate_positions(positions, feature_map, account_summary, pos_mode)
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
            "system_notes": [
                "這是第40步收尾試跑版：在每日實單-GPT-機器人協商式優化之上，補強持倉生命週期、分段止盈、保本切換、追蹤刷新。",
                "第40步新增：AI 可做 TP1/TP2 分段止盈、保本切換、追蹤刷新節奏、加倉後保護單重算。",
                f"ENABLE_LIVE_EXECUTION={settings.enable_live_execution}",
                f"OKX_IS_DEMO={settings.okx_is_demo}",
                f"KILL_SWITCH={settings.kill_switch}",
                f"posMode={pos_mode}",
                f"tdMode={settings.td_mode}",
                f"GPT_DAILY_REVIEW_READY={self.gpt.available()}",
                f"consecutive_losses={trade_summary['consecutive_losses']}/{settings.max_consecutive_losses_before_pause}",
                "市場模板與全市場基礎型態資料只做輔助特徵，不做硬性限制。",
                "AI 直接控制 entry / sizing / leverage / protection / exit。",
                "Step40 已收尾整理，適合先上傳試跑；核心仍是每日實單→GPT分析→機器人審議→討論收斂→再套用到交易行為。",
            ],
        }
        self.dashboard.update(payload)
        self.logger.info(
            "step40 done. watch=%s positions=%s executed=%s autonomy=%.2f risk_blocked=%s daily_review=%s",
            len(watchlist),
            len(positions),
            len(executed_orders),
            autonomy.get("autonomy_ratio", 0.0),
            risk_row.get("blocked"),
            daily_review.get("reason", daily_review.get("day", "ok")),
        )
        return payload
