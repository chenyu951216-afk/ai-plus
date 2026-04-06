import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool) -> bool:
    value = os.getenv(key, str(default)).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _get_first_env(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    return ""


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "okx-ai-futures-live-autonomy").strip()
    app_env: str = os.getenv("APP_ENV", "production")

    okx_api_key: str = _get_first_env(
        "OKX_API_KEY",
        "OKX_KEY",
        "OKX_ACCESS_KEY",
    )
    okx_api_secret: str = _get_first_env(
        "OKX_API_SECRET",
        "OKX_SECRET",
        "OKX_SECRET_KEY",
        "OKX_ACCESS_SECRET",
    )
    okx_api_passphrase: str = _get_first_env(
        "OKX_API_PASSPHRASE",
        "OKX_PASSPHRASE",
        "OKX_ACCESS_PASSPHRASE",
    )
    okx_base_url: str = os.getenv("OKX_BASE_URL", "https://www.okx.com").strip()
    okx_is_demo: bool = (
        _get_bool("OKX_IS_DEMO", False)
        or _get_bool("OKX_DEMO", False)
        or _get_bool("USE_OKX_DEMO", False)
    )

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    enable_gpt_reflection: bool = _get_bool("ENABLE_GPT_REFLECTION", True)
    gpt_model: str = os.getenv("GPT_MODEL", "gpt-5.4").strip()
    gpt_timeout_sec: float = float(os.getenv("GPT_TIMEOUT_SEC", "30"))
    gpt_reasoning_effort: str = os.getenv("GPT_REASONING_EFFORT", "medium").strip()

    instrument_type: str = os.getenv("INSTRUMENT_TYPE", "SWAP").strip()
    primary_timeframe: str = os.getenv("PRIMARY_TIMEFRAME", "15m").strip()
    scan_top_n: int = int(os.getenv("SCAN_TOP_N", "50"))
    scan_symbol_interval_sec: float = float(os.getenv("SCAN_SYMBOL_INTERVAL_SEC", "0.005"))
    candle_limit: int = int(os.getenv("CANDLE_LIMIT", "240"))

    runtime_loop_enabled: bool = _get_bool("RUNTIME_LOOP_ENABLED", True)
    runtime_loop_sleep_sec: float = float(os.getenv("RUNTIME_LOOP_SLEEP_SEC", "50"))

    enable_live_execution: bool = _get_bool("ENABLE_LIVE_EXECUTION", True)
    enable_position_sync: bool = _get_bool("ENABLE_POSITION_SYNC", True)
    enable_protective_orders: bool = _get_bool("ENABLE_PROTECTIVE_ORDERS", True)
    enable_position_manager: bool = _get_bool("ENABLE_POSITION_MANAGER", True)
    enable_position_lifecycle: bool = _get_bool("ENABLE_POSITION_LIFECYCLE", True)

    kill_switch: bool = _get_bool("KILL_SWITCH", False)
    require_credentials_check: bool = _get_bool("REQUIRE_CREDENTIALS_CHECK", True)
    require_account_config_check: bool = _get_bool("REQUIRE_ACCOUNT_CONFIG_CHECK", True)
    require_max_avail_check: bool = _get_bool("REQUIRE_MAX_AVAIL_CHECK", True)

    max_live_entries_per_cycle: int = int(os.getenv("MAX_LIVE_ENTRIES_PER_CYCLE", "4"))
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "10"))
    max_total_risk_pct: float = float(os.getenv("MAX_TOTAL_RISK_PCT", "0.18"))
    max_consecutive_losses_before_pause: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES_BEFORE_PAUSE", "10"))

    min_trade_confidence: float = float(os.getenv("MIN_TRADE_CONFIDENCE", "0.53"))
    min_watch_confidence: float = float(os.getenv("MIN_WATCH_CONFIDENCE", "0.42"))

    max_add_position_multiplier: float = float(os.getenv("MAX_ADD_POSITION_MULTIPLIER", "1.8"))
    hard_stop_loss_pct: float = float(os.getenv("HARD_STOP_LOSS_PCT", "0.012"))
    min_lock_profit_pct: float = float(os.getenv("MIN_LOCK_PROFIT_PCT", "0.002"))
    break_even_trigger_rr: float = float(os.getenv("BREAK_EVEN_TRIGGER_RR", "1.0"))
    trailing_activation_rr: float = float(os.getenv("TRAILING_ACTIVATION_RR", "1.4"))
    trailing_buffer_atr: float = float(os.getenv("TRAILING_BUFFER_ATR", "0.8"))

    initial_stop_loss_atr: float = float(os.getenv("INITIAL_STOP_LOSS_ATR", "1.8"))
    initial_take_profit_atr: float = float(os.getenv("INITIAL_TAKE_PROFIT_ATR", "3.0"))

    default_leverage_min: int = int(os.getenv("DEFAULT_LEVERAGE_MIN", "3"))
    default_leverage_max: int = int(os.getenv("DEFAULT_LEVERAGE_MAX", "20"))
    default_margin_pct_min: float = float(os.getenv("DEFAULT_MARGIN_PCT_MIN", "0.01"))
    default_margin_pct_max: float = float(os.getenv("DEFAULT_MARGIN_PCT_MAX", "0.08"))

    adaptive_min_trade_confidence_floor: float = float(os.getenv("ADAPTIVE_MIN_TRADE_CONFIDENCE_FLOOR", "0.45"))
    adaptive_min_trade_confidence_ceiling: float = float(os.getenv("ADAPTIVE_MIN_TRADE_CONFIDENCE_CEILING", "0.72"))
    adaptive_size_floor: float = float(os.getenv("ADAPTIVE_SIZE_FLOOR", "0.35"))
    adaptive_size_ceiling: float = float(os.getenv("ADAPTIVE_SIZE_CEILING", "2.4"))
    adaptive_leverage_floor: int = int(os.getenv("ADAPTIVE_LEVERAGE_FLOOR", "2"))
    adaptive_leverage_ceiling: int = int(os.getenv("ADAPTIVE_LEVERAGE_CEILING", "25"))

    lifecycle_min_position_size: float = float(os.getenv("LIFECYCLE_MIN_POSITION_SIZE", "1.0"))
    lifecycle_add_threshold: float = float(os.getenv("LIFECYCLE_ADD_THRESHOLD", "0.78"))
    lifecycle_reduce_threshold: float = float(os.getenv("LIFECYCLE_REDUCE_THRESHOLD", "0.32"))
    lifecycle_partial_take_profit_rr: float = float(os.getenv("LIFECYCLE_PARTIAL_TAKE_PROFIT_RR", "1.6"))
    lifecycle_reduce_fraction: float = float(os.getenv("LIFECYCLE_REDUCE_FRACTION", "0.25"))
    lifecycle_add_fraction: float = float(os.getenv("LIFECYCLE_ADD_FRACTION", "0.35"))
    lifecycle_max_scale_ins_per_position: int = int(os.getenv("LIFECYCLE_MAX_SCALE_INS_PER_POSITION", "2"))
    lifecycle_max_partial_exits_per_position: int = int(os.getenv("LIFECYCLE_MAX_PARTIAL_EXITS_PER_POSITION", "2"))
    lifecycle_tp1_fraction: float = float(os.getenv("LIFECYCLE_TP1_FRACTION", "0.25"))
    lifecycle_tp2_fraction: float = float(os.getenv("LIFECYCLE_TP2_FRACTION", "0.35"))
    lifecycle_break_even_lock_ratio: float = float(os.getenv("LIFECYCLE_BREAK_EVEN_LOCK_RATIO", "0.15"))
    lifecycle_trailing_step_rr: float = float(os.getenv("LIFECYCLE_TRAILING_STEP_RR", "0.45"))
    lifecycle_protection_refresh_cooldown_sec: int = int(os.getenv("LIFECYCLE_PROTECTION_REFRESH_COOLDOWN_SEC", "120"))

    td_mode: str = os.getenv("TD_MODE", "cross").strip()
    force_pos_side_in_net_mode: bool = _get_bool("FORCE_POS_SIDE_IN_NET_MODE", False)

    ai_controls_entry: bool = _get_bool("AI_CONTROLS_ENTRY", True)
    ai_controls_sizing: bool = _get_bool("AI_CONTROLS_SIZING", True)
    ai_controls_leverage: bool = _get_bool("AI_CONTROLS_LEVERAGE", True)
    ai_controls_protection: bool = _get_bool("AI_CONTROLS_PROTECTION", True)
    ai_controls_exit: bool = _get_bool("AI_CONTROLS_EXIT", True)
    ai_controls_parameter_adaptation: bool = _get_bool("AI_CONTROLS_PARAMETER_ADAPTATION", True)
    autonomy_required_ratio: float = float(os.getenv("AUTONOMY_REQUIRED_RATIO", "1.0"))

    enable_daily_gpt_review: bool = _get_bool("ENABLE_DAILY_GPT_REVIEW", True)
    daily_review_min_trades: int = int(os.getenv("DAILY_REVIEW_MIN_TRADES", "6"))
    gpt_deliberation_rounds: int = int(os.getenv("GPT_DELIBERATION_ROUNDS", "3"))
    gpt_review_timezone: str = os.getenv("GPT_REVIEW_TIMEZONE", "Asia/Taipei").strip()

    data_dir: str = os.getenv("DATA_DIR", "data").strip()
    state_dir: str = os.getenv("STATE_DIR", "state").strip()

    set_leverage_before_entry: bool = _get_bool("SET_LEVERAGE_BEFORE_ENTRY", True)
    skip_protective_if_entry_failed: bool = _get_bool("SKIP_PROTECTIVE_IF_ENTRY_FAILED", True)

    ui_host: str = os.getenv("UI_HOST", "0.0.0.0").strip()
    ui_port: int = int(os.getenv("UI_PORT", "8090"))


settings = Settings()
