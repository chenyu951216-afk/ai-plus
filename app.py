import logging

from memory.backup_memory import ProjectMemoryBackup
from services.runtime_loop_service import RuntimeLoopService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> None:
    backup = ProjectMemoryBackup()
    backup.add_record(
        step_title="Step 40 - 試跑前收尾整合版",
        change_reason=(
            "在第39步的每日實單-GPT協商與持倉生命週期管理之上，"
            "補齊分段止盈、保本切換、追蹤刷新節奏與加倉後保護單重算，作為上傳試跑前的收尾版本。"
        ),
        changed_files=[
            "app.py",
            "config/settings.py",
            "ai/adaptive_policy_store.py",
            "ai/autonomy_controller.py",
            "services/order_execution_service.py",
            "services/exit_execution_service.py",
            "services/protective_order_service.py",
            "services/position_manager_service.py",
            "services/daily_trade_digest_service.py",
            "services/gpt_advisor_service.py",
            "services/optimization_apply_service.py",
            "services/trading_runtime_service.py",
            "storage/position_lifecycle_store.py",
            ".env.example",
            "README.md",
            ".gitignore",
        ],
        detail=(
            "第40步把持倉管理做收尾：新增 TP1/TP2、保本與追蹤刷新節奏、生命周期狀態保存，"
            "並整理 README / env / gitignore，方便直接上傳試跑。"
        ),
        tags=["step40", "trial_run", "lifecycle", "tp1_tp2", "break_even", "trailing_refresh"],
    )
    RuntimeLoopService().run_forever()


if __name__ == "__main__":
    main()
