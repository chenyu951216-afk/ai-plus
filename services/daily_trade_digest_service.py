from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from config.settings import settings
from storage.trade_store import TradeStore


class DailyTradeDigestService:
    def __init__(self) -> None:
        self.store = TradeStore()

    def today_key(self) -> str:
        return datetime.now(ZoneInfo(settings.gpt_review_timezone)).date().isoformat()

    def build_digest(self, day: str | None = None) -> Dict[str, Any]:
        target_day = day or self.today_key()
        rows = self.store.records_for_day(target_day, settings.gpt_review_timezone)
        if not rows:
            return {"day": target_day, "trade_count": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0, "avg_drawdown": 0.0, "sides": {}, "regimes": {}, "exit_reasons": {}, "management_actions": {}, "protection_states": {}, "lifecycle_stages": {}, "areas": {}, "best_symbols": [], "worst_symbols": [], "trades": []}

        wins = [r for r in rows if float(r.get("pnl", 0.0) or 0.0) > 0]
        losses = [r for r in rows if float(r.get("pnl", 0.0) or 0.0) <= 0]
        area_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "avg_pnl": 0.0})
        symbol_pnls: Dict[str, List[float]] = defaultdict(list)
        exit_reason_counter: Counter[str] = Counter()
        side_counter: Counter[str] = Counter()
        regime_counter: Counter[str] = Counter()
        management_counter: Counter[str] = Counter()
        protection_counter: Counter[str] = Counter()
        lifecycle_stage_counter: Counter[str] = Counter()

        for row in rows:
            pnl = float(row.get("pnl", 0.0) or 0.0)
            symbol = str(row.get("symbol", ""))
            area = str(row.get("review_area", row.get("reason", "general")))
            area_stats[area]["count"] += 1
            symbol_pnls[symbol].append(pnl)
            exit_reason_counter[str(row.get("reason", "unknown"))] += 1
            side_counter[str(row.get("side", "unknown"))] += 1
            regime_counter[str(row.get("market_regime", "unknown"))] += 1
            management_counter[str(row.get("management_action", "none"))] += 1
            protection_counter[str(row.get("protection_state", row.get("protection_profile", "unknown")))] += 1
            lifecycle_stage_counter[str(row.get("lifecycle_stage", "none"))] += 1

        for key, value in area_stats.items():
            matching = [float(r.get("pnl", 0.0) or 0.0) for r in rows if str(r.get("review_area", r.get("reason", "general"))) == key]
            value["avg_pnl"] = round(mean(matching), 6) if matching else 0.0

        best_symbols = sorted(({"symbol": sym, "avg_pnl": round(mean(vals), 6), "trades": len(vals)} for sym, vals in symbol_pnls.items()), key=lambda x: x["avg_pnl"], reverse=True)[:8]
        worst_symbols = sorted(({"symbol": sym, "avg_pnl": round(mean(vals), 6), "trades": len(vals)} for sym, vals in symbol_pnls.items()), key=lambda x: x["avg_pnl"])[:8]

        compact_trades = []
        for row in rows[-50:]:
            compact_trades.append({
                "timestamp": row.get("timestamp"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "pnl": row.get("pnl"),
                "drawdown": row.get("drawdown"),
                "entry_confidence": row.get("entry_confidence"),
                "trend_bias": row.get("trend_bias"),
                "market_regime": row.get("market_regime"),
                "pre_breakout_score": row.get("pre_breakout_score"),
                "size": row.get("size"),
                "size_multiplier": row.get("size_multiplier"),
                "leverage": row.get("leverage"),
                "margin_pct": row.get("margin_pct"),
                "reason": row.get("reason"),
                "exit_style": row.get("exit_style"),
                "protection_profile": row.get("protection_profile"),
                "position_management_profile": row.get("position_management_profile"),
                "management_action": row.get("management_action", "none"),
                "protection_state": row.get("protection_state", row.get("protection_profile")),
                "lifecycle_stage": row.get("lifecycle_stage", "none"),
            })

        return {
            "day": target_day,
            "trade_count": len(rows),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / max(len(rows), 1), 6),
            "avg_pnl": round(mean(float(r.get("pnl", 0.0) or 0.0) for r in rows), 6),
            "total_pnl": round(sum(float(r.get("pnl", 0.0) or 0.0) for r in rows), 6),
            "avg_drawdown": round(mean(float(r.get("drawdown", 0.0) or 0.0) for r in rows), 6),
            "sides": dict(side_counter),
            "regimes": dict(regime_counter),
            "exit_reasons": dict(exit_reason_counter),
            "management_actions": dict(management_counter),
            "protection_states": dict(protection_counter),
            "lifecycle_stages": dict(lifecycle_stage_counter),
            "areas": {k: {"count": int(v["count"]), "avg_pnl": v["avg_pnl"]} for k, v in area_stats.items()},
            "best_symbols": best_symbols,
            "worst_symbols": worst_symbols,
            "trades": compact_trades,
        }
