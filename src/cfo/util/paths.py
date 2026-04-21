"""Centralized path constants. Test-overridable via env vars."""
import os
from pathlib import Path


DEFAULT_DATA_DIR = Path.home() / "Developer" / "Robinhood" / "data"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "cfo"
DEFAULT_RH_CONFIG_DIR = Path.home() / ".config" / "rh"


def data_dir() -> Path:
    override = os.environ.get("CFO_DATA_DIR")
    return Path(override) if override else DEFAULT_DATA_DIR


def config_dir() -> Path:
    override = os.environ.get("CFO_CONFIG_DIR")
    return Path(override) if override else DEFAULT_CONFIG_DIR


def rh_config_dir() -> Path:
    override = os.environ.get("CFO_RH_CONFIG_DIR")
    return Path(override) if override else DEFAULT_RH_CONFIG_DIR


def accounts_json() -> Path:
    return data_dir() / "portfolio" / "accounts.json"


def profile_md() -> Path:
    return data_dir() / "portfolio" / "profile.md"


def audit_log() -> Path:
    return data_dir() / "audit" / "cfo-actions.jsonl"


def tradebook_master() -> Path:
    return data_dir() / "tradebook" / "master.jsonl"


def schedules_json() -> Path:
    return config_dir() / "schedules.json"


def tax_lots_json() -> Path:
    return data_dir() / "tradebook" / "tax-lots.json"


def rh_raw_trades_jsonl() -> Path:
    return rh_config_dir() / "trades.jsonl"


def strategies_dir() -> Path:
    return data_dir() / "strategies"


def paper_strategies_dir() -> Path:
    return data_dir() / "paper" / "strategies"


def paper_composite_dir() -> Path:
    return data_dir() / "paper" / "composite"


def price_log_dir() -> Path:
    return data_dir() / "price-log"


def reports_dir() -> Path:
    return data_dir() / "reports"


def portfolio_history_dir() -> Path:
    return data_dir() / "portfolio" / "history"


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"
