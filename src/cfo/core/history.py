"""Portfolio historical snapshots (month-end)."""
import json
from datetime import datetime, timezone
from pathlib import Path

from cfo.core import portfolio as core_p
from cfo.util import atomic, paths


def _snapshot_path(label: str) -> Path:
    return paths.portfolio_history_dir() / f"{label}.json"


def snapshot_current(label: str) -> Path:
    """Freeze the current accounts.json into data/portfolio/history/<label>.json."""
    af = core_p.load()
    total = sum(a.balance for a in af.accounts)
    payload = {
        "schema_version": 1,
        "label": label,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": total,
        "accounts": [a.model_dump(mode="json", exclude_none=True) for a in af.accounts],
    }
    p = _snapshot_path(label)
    atomic.write_json(p, payload)
    return p


def load(label: str) -> dict | None:
    p = _snapshot_path(label)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def total_delta(prev_label: str, curr_label: str) -> float | None:
    """Return total_curr - total_prev, or None if either missing."""
    prev = load(prev_label)
    curr = load(curr_label)
    if prev is None or curr is None:
        return None
    return float(curr["total"]) - float(prev["total"])
