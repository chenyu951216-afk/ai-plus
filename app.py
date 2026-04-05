import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from memory.backup_memory import ProjectMemoryBackup
from services.runtime_loop_service import RuntimeLoopService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("app")

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "ui"
TEMPLATES_DIR = UI_DIR / "templates"

app = Flask(__name__)


def _write_step40_backup() -> None:
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


def _run_runtime_loop() -> None:
    try:
        logger.info("Starting trading runtime loop thread.")
        RuntimeLoopService().run_forever()
    except Exception:
        logger.exception("Runtime loop crashed.")


@app.route("/")
def home():
    index_html = UI_DIR / "index.html"
    dashboard_html = TEMPLATES_DIR / "dashboard.html"

    if index_html.exists():
        return send_from_directory(UI_DIR, "index.html")
    if dashboard_html.exists():
        return send_from_directory(TEMPLATES_DIR, "dashboard.html")

    return jsonify(
        {
            "status": "ok",
            "service": "okx-ai-trading-bot",
            "message": "runtime loop is running in background",
            "ui": "not found",
        }
    )


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


@app.route("/ui")
def serve_ui():
    index_html = UI_DIR / "index.html"
    dashboard_html = TEMPLATES_DIR / "dashboard.html"

    if index_html.exists():
        return send_from_directory(UI_DIR, "index.html")
    if dashboard_html.exists():
        return send_from_directory(TEMPLATES_DIR, "dashboard.html")

    return jsonify({"status": "error", "message": "UI file not found"}), 404


@app.route("/ui/<path:filename>")
def serve_ui_assets(filename: str):
    direct_file = UI_DIR / filename
    template_file = TEMPLATES_DIR / filename

    if direct_file.exists() and direct_file.is_file():
        return send_from_directory(UI_DIR, filename)

    if template_file.exists() and template_file.is_file():
        return send_from_directory(TEMPLATES_DIR, filename)

    return jsonify({"status": "error", "message": f"Asset not found: {filename}"}), 404


def main() -> None:
    _write_step40_backup()

    runtime_thread = threading.Thread(
        target=_run_runtime_loop,
        daemon=True,
        name="runtime-loop-thread",
    )
    runtime_thread.start()

    port = int(os.environ.get("PORT", "8080"))
    logger.info("Starting web server on 0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port)
from services.account_service import AccountService
from services.trading_runtime_service import TradingRuntimeService

account_service = AccountService()
runtime_service = TradingRuntimeService()


@app.route("/api/account")
def api_account():
    try:
        data = account_service.get_account_summary()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/positions")
def api_positions():
    try:
        data = runtime_service.get_positions_snapshot()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orders")
def api_orders():
    try:
        data = runtime_service.get_recent_orders()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai/status")
def api_ai_status():
    try:
        return jsonify({
            "autonomy": 1.0,
            "status": "running"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    main()
