from typing import Dict, Any
from storage.state_store import StateStore

class DashboardStateService:
    def __init__(self) -> None:
        self.store = StateStore()

    def update(self, payload: Dict[str, Any]) -> None:
        self.store.save(payload)

    def read(self) -> Dict[str, Any]:
        return self.store.load()
