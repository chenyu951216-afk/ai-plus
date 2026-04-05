from typing import Dict, Any

class BaseScorer:
    def score(self, features: Dict[str, Any]) -> Dict[str, Any]:
        score = 0.0
        if features.get("trend_bias") == "bullish":
            score += 0.12
        elif features.get("trend_bias") == "bearish":
            score -= 0.12
        score += float(features.get("pre_breakout_score", 0.0)) * 0.22
        confidence = max(min((score + 1) / 2, 1.0), 0.0)
        return {"model_name": "base", "raw_score": max(min(score, 1.0), -1.0), "confidence": confidence}
