"""Tests for daily price-log collector."""
import json
from datetime import date, datetime, timezone

from cfo.core import price_log
from cfo.util import paths


def test_snap_writes_jsonl(tmp_data_dir, monkeypatch):
    def fake_quote(sym):
        return {"symbol": sym, "last_price": 100.0, "updated_at": "2026-04-21T02:10:34Z"}
    from cfo.core import rh_bridge
    monkeypatch.setattr(rh_bridge, "quote", fake_quote)
    n = price_log.snap(["VOO", "QQQM"])
    assert n == 2
    today = date.today().isoformat()
    out = paths.price_log_dir() / today / "quotes.jsonl"
    assert out.exists()
    lines = out.read_text().strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        rec = json.loads(line)
        assert "last_price" in rec
        assert "cfo_snap_ts" in rec


def test_snap_skips_failures(tmp_data_dir, monkeypatch):
    """One failing quote should not abort the whole snap."""
    def fake_quote(sym):
        if sym == "BADSYM":
            raise RuntimeError("symbol not found")
        return {"symbol": sym, "last_price": 50.0, "updated_at": "2026-04-21T02:10:34Z"}
    from cfo.core import rh_bridge
    monkeypatch.setattr(rh_bridge, "quote", fake_quote)
    n = price_log.snap(["VOO", "BADSYM", "QQQM"])
    assert n == 2


def test_watchlist_from_holdings(tmp_data_dir):
    from datetime import datetime, timezone
    from cfo.core import portfolio as core_p
    from cfo.schemas.portfolio import (
        Account,
        AccountsFile,
        AccountSource,
        AccountType,
        Holding,
    )
    core_p.save(
        AccountsFile(
            schema_version=1,
            last_updated=datetime.now(timezone.utc),
            accounts=[
                Account(
                    id="rh-individual",
                    type=AccountType.taxable,
                    broker="robinhood",
                    source=AccountSource.rh_sync,
                    balance=1000,
                    holdings=[Holding(symbol="TSLA", qty=1), Holding(symbol="VOO", qty=2)],
                )
            ],
        )
    )
    wl = price_log.default_watchlist()
    assert "TSLA" in wl
    assert "VOO" in wl


def test_watchlist_from_file(tmp_data_dir):
    wl_file = paths.price_log_dir() / "watchlist.txt"
    wl_file.parent.mkdir(parents=True, exist_ok=True)
    wl_file.write_text("VOO\nQQQM\n# comment\n\n NVDA \n")
    wl = price_log.default_watchlist()
    assert set(wl) >= {"VOO", "QQQM", "NVDA"}


def test_watchlist_empty(tmp_data_dir):
    """No holdings, no watchlist.txt → empty list."""
    assert price_log.default_watchlist() == []


def test_show_returns_history(tmp_data_dir, monkeypatch):
    from cfo.core import rh_bridge
    monkeypatch.setattr(
        rh_bridge,
        "quote",
        lambda s: {"symbol": s, "last_price": 100, "updated_at": "2026-04-21T02:10:34Z"},
    )
    price_log.snap(["VOO"])
    history = price_log.show("VOO", days=1)
    assert len(history) == 1
    assert history[0]["symbol"] == "VOO"


def test_show_missing_symbol(tmp_data_dir):
    assert price_log.show("NONE", days=7) == []
