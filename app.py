import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, send_from_directory

from memory.backup_memory import ProjectMemoryBackup
from services.runtime_loop_service import RuntimeLoopService
from services.account_service import AccountService
from services.trading_runtime_service import TradingRuntimeService
from services.dashboard_state_service import DashboardStateService

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
dashboard_state_service = DashboardStateService()

_runtime_started = False
_runtime_lock = threading.Lock()


def _write_step40_backup() -> None:
    backup = ProjectMemoryBackup()
    backup.add_record(
        step_title="Step 40 - 試跑前收尾整合版",
        change_reason="部署版啟動修正、UI 與 API 掛載修正。",
        changed_files=["app.py"],
        detail="修正 gunicorn 下背景執行緒未啟動問題，並補 dashboard API 路徑。",
        tags=["step40", "deploy", "gunicorn", "ui", "api"],
    )


def _run_runtime_loop() -> None:
    try:
        logger.info("Starting trading runtime loop thread.")
        RuntimeLoopService().run_forever()
    except Exception:
        logger.exception("Runtime loop crashed.")


def _start_background_runtime_once() -> None:
    global _runtime_started
    with _runtime_lock:
        if _runtime_started:
            return
        _write_step40_backup()
        runtime_thread = threading.Thread(
            target=_run_runtime_loop,
            daemon=True,
            name="runtime-loop-thread",
        )
        runtime_thread.start()
        _runtime_started = True
        logger.info("Background runtime thread started.")


def _serve_dashboard_or_fallback():
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


def _json_ok(data: Any):
    return jsonify(data)


def _json_error(exc: Exception, code: int = 500):
    logger.exception("API error: %s", exc)
    return jsonify({"error": str(exc)}), code


@app.route("/")
def home():
    return _serve_dashboard_or_fallback()


@app.route("/ui")
def serve_ui():
    return _serve_dashboard_or_fallback()


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "healthy",
            "runtime_started": _runtime_started,
        }
    )


@app.route("/ui/<path:filename>")
def serve_ui_assets(filename: str):
    direct_file = UI_DIR / filename
    template_file = TEMPLATES_DIR / filename

    if direct_file.exists() and direct_file.is_file():
        return send_from_directory(UI_DIR, filename)

    if template_file.exists() and template_file.is_file():
        return send_from_directory(TEMPLATES_DIR, filename)

    return jsonify({"status": "error", "message": f"Asset not found: {filename}"}), 404


# -------------------------
# Dashboard / API endpoints
# -------------------------

@app.route("/api/account")
def api_account():
    try:
        return _json_ok(account_service.get_account_summary())
    except Exception as e:
        return _json_error(e)


@app.route("/api/positions")
def api_positions():
    try:
        if hasattr(runtime_service, "get_positions_snapshot"):
            return _json_ok(runtime_service.get_positions_snapshot())
        client = getattr(runtime_service, "client", None)
        if client and hasattr(client, "safe_get_positions"):
            payload = client.safe_get_positions()
            return _json_ok(payload.get("data", []))
        return _json_ok([])
    except Exception as e:
        return _json_error(e)


@app.route("/api/orders")
def api_orders():
    try:
        if hasattr(runtime_service, "get_recent_orders"):
            return _json_ok(runtime_service.get_recent_orders())
        return _json_ok([])
    except Exception as e:
        return _json_error(e)


@app.route("/api/ai/status")
def api_ai_status():
    return _json_ok({"autonomy": 1.0, "status": "running"})


@app.route("/api/dashboard")
@app.route("/api/dashboard_state")
@app.route("/api/state")
def api_dashboard_state():
    try:
        if hasattr(dashboard_state_service, "build_state"):
            return _json_ok(dashboard_state_service.build_state())
        if hasattr(dashboard_state_service, "get_state"):
            return _json_ok(dashboard_state_service.get_state())
        if hasattr(dashboard_state_service, "snapshot"):
            return _json_ok(dashboard_state_service.snapshot())

        # fallback
        account = account_service.get_account_summary()
        positions = []
        if hasattr(runtime_service, "get_positions_snapshot"):
            positions = runtime_service.get_positions_snapshot()

        return _json_ok(
            {
                "account": account,
                "positions": positions,
                "orders": [],
                "watchlist": [],
                "protective_orders": [],
                "reflection": "",
                "position_management": [],
                "role_audit": [],
                "system_note": "fallback dashboard state",
                "autonomy_ratio": 1.0,
            }
        )
    except Exception as e:
        return _json_error(e)


@app.route("/api/runtime_status")
def api_runtime_status():
    return _json_ok(
        {
            "runtime_started": _runtime_started,
            "service": "okx-ai-trading-bot",
        }
    )


# gunicorn 載入模組時就啟動背景 loop
_start_background_runtime_once()


def main() -> None:
    _start_background_runtime_once()
    port = int(os.environ.get("PORT", "8080"))
    logger.info("Starting web server on 0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
