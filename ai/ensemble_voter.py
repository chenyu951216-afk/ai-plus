from typing import Dict, Any, List

class EnsembleVoter:
    def vote(self, model_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not model_outputs:
            return {"ensemble_score": 0.0, "ensemble_confidence": 0.0}
        score = sum(float(x.get("raw_score", 0.0)) for x in model_outputs) / len(model_outputs)
        conf = sum(float(x.get("confidence", 0.0)) for x in model_outputs) / len(model_outputs)
        return {"ensemble_score": score, "ensemble_confidence": conf}
