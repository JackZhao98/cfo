"""Price log collector — daily snapshot of quotes."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cfo.core import portfolio as core_portfolio
from cfo.core import rh_bridge
from cfo.util import atomic, paths


def _snap_file(d: date) -> Path:
    return paths.price_log_dir() / d.isoformat() / "quotes.jsonl"


def default_watchlist() -> list[str]:
    """Union of holdings across all accounts + symbols in watchlist.txt."""
    symbols: set[str] = set()
    af = core_portfolio.load()
    for a in af.accounts:
        for h in a.holdings:
            if h.symbol:
                symbols.add(h.symbol.upper())
    wl_file = paths.price_log_dir() / "watchlist.txt"
    if wl_file.exists():
        for line in wl_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            symbols.add(line.upper())
    return sorted(symbols)


def snap(symbols: list[str]) -> int:
    """Fetch each symbol via rh_bridge.quote and append to today's jsonl.

    Individual failures are skipped (logged but not raised) so one bad symbol
    doesn't abort the whole batch.
    """
    today = date.today()
    path = _snap_file(today)
    count = 0
    for sym in symbols:
        try:
            rec = rh_bridge.quote(sym)
        except RuntimeError:
            continue
        rec["cfo_snap_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        atomic.append_jsonl(path, rec)
        count += 1
    return count


def show(symbol: str, days: int = 7) -> list[dict]:
    """Return records for symbol across last N days (inclusive of today)."""
    out: list[dict] = []
    today = date.today()
    for i in range(days):
        d = today - timedelta(days=i)
        p = _snap_file(d)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("symbol", "").upper() == symbol.upper():
                out.append(rec)
    return out
