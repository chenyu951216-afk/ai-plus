import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

# 🔥 這兩個一定要放上面（關鍵）
from services.account_service import AccountService
from services.trading_runtime_service import TradingRuntimeService

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

account_service = AccountService()
runtime_service = TradingRuntimeService()


def _write_step40_backup() -> None:
    backup = ProjectMemoryBackup()
    backup.add_record(
        step_title="Step 40 - 試跑前收尾整合版",
        change_reason="final integration",
        changed_files=["app.py"],
        detail="final",
        tags=["step40"],
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
    if index_html.exists():
        return send_from_directory(UI_DIR, "index.html")

    return jsonify({
        "status": "ok",
        "message": "runtime loop is running"
    })


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


# ======================
# 🔥 API（現在會正常了）
# ======================

@app.route("/api/account")
def api_account():
    try:
        return jsonify(account_service.get_account_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/positions")
def api_positions():
    try:
        return jsonify(runtime_service.get_positions_snapshot())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orders")
def api_orders():
    try:
        return jsonify(runtime_service.get_recent_orders())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai/status")
def api_ai_status():
    return jsonify({
        "autonomy": 1.0,
        "status": "running"
    })


def main():
    _write_step40_backup()

    threading.Thread(
        target=_run_runtime_loop,
        daemon=True
    ).start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
