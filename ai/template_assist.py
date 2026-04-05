from typing import Any, Dict

from ai.market_knowledge_base import MarketKnowledgeBase


class TemplateAssist:
    """
    市場模板只提供參考，不直接做硬限制。
    這裡整合全市場常見基礎型態 / 趨勢 / 波動 / 流動性特徵，供 AI 學習參考。
    """

    def __init__(self) -> None:
        self.market_base = MarketKnowledgeBase()

    def build(self, features: Dict[str, Any]) -> Dict[str, Any]:
        base = self.market_base.evaluate(features)
        templates = list(base.get("market_basis_templates", []))
        return {
            "template_hints": templates,
            "template_long_bias": float(base.get("market_long_bias", 0.0) or 0.0),
            "template_short_bias": float(base.get("market_short_bias", 0.0) or 0.0),
            "template_observe_bias": float(base.get("market_observe_bias", 0.0) or 0.0),
            "template_summary": str(base.get("market_basis_summary", "")),
            "market_basis_snapshot": base.get("market_basis_snapshot", {}),
            "market_basis_categories": base.get("market_basis_categories", []),
        }
