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


def ensure_parent(path: Path) -> None:
    """Create parent directory if it doesn't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
