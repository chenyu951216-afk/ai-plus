from dataclasses import dataclass, asdict
from typing import Dict, List

@dataclass
class ModelRole:
    role: str
    owner: str
    status: str
    description: str

class ModelRegistry:
    def __init__(self) -> None:
        self.roles: List[ModelRole] = [
            ModelRole("entry_decision", "ai", "active", "AI 決定進場與方向。"),
            ModelRole("position_sizing", "ai", "active", "AI 決定倉位強度。"),
            ModelRole("leverage_margin", "ai", "active", "AI 決定槓桿與保證金比例。"),
            ModelRole("protection_logic", "ai", "active", "AI 決定保本、trailing、利潤保護。"),
            ModelRole("exit_decision", "ai", "active", "AI 決定退出時機。"),
            ModelRole("parameter_adaptation", "ai", "active", "AI 根據結果微調策略參數。"),
            ModelRole("safety_limits", "system", "active", "系統只保留安全上限，不直接替代交易決策。"),
        ]

    def summary(self) -> List[Dict]:
        return [asdict(x) for x in self.roles]

    def autonomy_ratio(self) -> float:
        ai_roles = sum(1 for x in self.roles if x.owner == "ai" and x.status == "active")
        trade_roles = sum(1 for x in self.roles if x.role != "safety_limits")
        return 0.0 if trade_roles == 0 else ai_roles / trade_roles
