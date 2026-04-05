import logging
import time
from config.settings import settings
from services.trading_runtime_service import TradingRuntimeService

class RuntimeLoopService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.runtime = TradingRuntimeService()

    def run_forever(self) -> None:
        if not settings.runtime_loop_enabled:
            self.runtime.run_once()
            return
        while True:
            try:
                self.runtime.run_once()
            except Exception as exc:
                self.logger.exception("runtime loop error: %s", exc)
            time.sleep(settings.runtime_loop_sleep_sec)
