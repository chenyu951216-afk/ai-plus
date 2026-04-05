from typing import Dict, Any
from ai.autonomy_controller import AIAutonomyController

class AutonomyAuditService:
    def __init__(self) -> None:
        self.controller = AIAutonomyController()

    def run(self) -> Dict[str, Any]:
        return self.controller.autonomy_report()
