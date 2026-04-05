from typing import Any, Dict, List

from ai.adaptive_policy_store import AdaptivePolicyStore
from config.settings import settings
from services.gpt_advisor_service import GPTAdvisorService


class SelfReflectionEngine:
    def __init__(self) -> None:
        self.policy_store = AdaptivePolicyStore()
        self.gpt = GPTAdvisorService()

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def summarize(self, recent_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        policy = self.policy_store.load()
        if not recent_results:
            policy["last_reflection"] = "目前尚無足夠結果，AI 先沿用現有自主策略。"
            saved = self.policy_store.save(policy)
            return {"plain_text": policy["last_reflection"], "adaptations": [], "policy": saved, "gpt_status": self.gpt.available()}

        wins = sum(1 for x in recent_results if float(x.get("pnl", 0.0) or 0.0) > 0)
        losses = sum(1 for x in recent_results if float(x.get("pnl", 0.0) or 0.0) <= 0)
        avg_pnl = sum(float(x.get("pnl", 0.0) or 0.0) for x in recent_results) / len(recent_results)

        adaptations: List[Dict[str, Any]] = []
        if losses > wins:
            policy["entry_confidence_shift"] = self._clamp(float(policy.get("entry_confidence_shift", 0.0)) + 0.012, -0.08, 0.08)
            policy["size_multiplier_bias"] = self._clamp(float(policy.get("size_multiplier_bias", 1.0)) - 0.05, settings.adaptive_size_floor, settings.adaptive_size_ceiling)
            adaptations.append({"target": "entry_selectivity", "action": "slightly_raise"})
        else:
            policy["entry_confidence_shift"] = self._clamp(float(policy.get("entry_confidence_shift", 0.0)) - 0.008, -0.08, 0.08)
            policy["size_multiplier_bias"] = self._clamp(float(policy.get("size_multiplier_bias", 1.0)) + 0.03, settings.adaptive_size_floor, settings.adaptive_size_ceiling)
            adaptations.append({"target": "sample_growth", "action": "slightly_expand"})

        summary = (
            f"AI 近期自我摘要：樣本數 {len(recent_results)}，勝 {wins}、負 {losses}，平均單筆損益 {avg_pnl:.4f}。"
            f"正式的深度優化請以每日實單 GPT 協商回圈為主。"
        )
        policy["last_reflection"] = summary
        saved = self.policy_store.save(policy)
        return {"plain_text": summary, "adaptations": adaptations, "policy": saved, "gpt_status": self.gpt.available()}

    def reflect(self, recent_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.summarize(recent_results)
