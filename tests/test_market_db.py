"""Tests for the market_db package."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from cfo.market_db import connection, parsers, schema
from cfo.market_db.dispatch import PARSER_REGISTRY, dispatch_parser
from cfo.market_db.live_sync import sync_live_market_data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect CFO data dir to tmp so market.db is isolated."""
    monkeypatch.setenv("CFO_DATA_DIR", str(tmp_path))
    # Fresh DB each test
    yield tmp_path / "market.db"


# ---------------------------------------------------------------------------
# Schema / connection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_init_creates_all_tables(tmp_db: Path):
    connection.init_db()
    assert tmp_db.exists()
    with sqlite3.connect(tmp_db) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    table_names = {r[0] for r in rows}
    # Core tables we rely on
    expected = {
        "schema_version",
        "sync_state",
        "ingest_log",
        "runs",
        "unknown_payloads",
        "quotes",
        "indexes",
        "option_chain",
        "news",
        "movers_scan",
        "sp500_movers",
        "accounts_snapshot",
        "holdings_snapshot",
        "activity",
        "dividends",
        "transfers",
    }
    missing = expected - table_names
    assert not missing, f"missing tables: {missing}"


@pytest.mark.unit
def test_init_is_idempotent(tmp_db: Path):
    connection.init_db()
    connection.init_db()
    with sqlite3.connect(tmp_db) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    assert rows[0] == 1


# ---------------------------------------------------------------------------
# Dispatch — authoritative command-based routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "command,expected",
    [
        (["rh", "quote", "SOFI", "--format", "json"], "parse_quote"),
        (["rh", "quote", "VOO", "QQQM", "SPY"], "parse_quote"),
        (["rh", "index", "VIX", "--format", "json"], "parse_index"),
        (["rh", "option", "chain", "SOFI", "--exp", "2026-05-22"], "parse_option_chain"),
        (["rh", "symbol", "news", "TSLA"], "parse_news"),
        (["rh", "scan", "--min-change", "10"], "parse_scan"),
        (["rh", "movers", "--direction", "up"], "parse_sp500_movers"),
        (["rh", "account", "snapshot"], "parse_account_snapshot"),
        (["rh", "activity", "--limit", "20"], "parse_activity"),
        (["rh", "dividends", "--limit", "50"], "parse_dividends"),
        (["rh", "transfers"], "parse_transfers"),
    ],
)
def test_dispatch_by_command(command, expected):
    assert dispatch_parser(command) == expected


@pytest.mark.unit
def test_dispatch_unknown_returns_none():
    assert dispatch_parser(["rh", "something-new"]) is None
    assert dispatch_parser([]) is None


@pytest.mark.unit
def test_dispatch_longest_prefix_match():
    # ('rh', 'option', 'chain') must beat ('rh', 'option') if both present
    assert dispatch_parser(["rh", "option", "chain", "SOFI"]) == "parse_option_chain"
    assert dispatch_parser(["rh", "option", "positions"]) == "parse_option_positions"


@pytest.mark.unit
def test_dispatch_ignores_schedule_name_semantics():
    """Dispatch must route purely by argv — no schedule name signal involved."""
    # Weird schedule names shouldn't matter:
    result = dispatch_parser(["rh", "quote", "SOFI"])
    assert result == "parse_quote"


@pytest.mark.unit
def test_registry_has_no_duplicate_values():
    """Every parser mapped is a callable in parsers.PARSER_IMPLEMENTATIONS."""
    for parser_name in PARSER_REGISTRY.values():
        assert parser_name in parsers.PARSER_IMPLEMENTATIONS, (
            f"{parser_name} missing from PARSER_IMPLEMENTATIONS"
        )


# ---------------------------------------------------------------------------
# Parser: quotes (single)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_quote_single(tmp_db: Path):
    connection.init_db()
    payload = {
        "symbol": "SOFI",
        "current_price": 19.18,
        "last_price": 19.15,
        "previous_close": 19.50,
        "day_change": -0.32,
        "day_change_pct": -1.6,
        "bid": 19.17,
        "ask": 19.19,
        "volume": 50_000_000,
        "high_52_weeks": 32.73,
        "low_52_weeks": 10.49,
        "market_cap": 24_000_000_000,
        "pe_ratio": 50.5,
        "updated_at": "2026-04-21T22:00:00Z",
    }
    meta = {
        "run_id": "run-abc",
        "command": ["rh", "quote", "SOFI", "--format", "json"],
        "finished_at": "2026-04-21T22:00:05Z",
        "created_at": "2026-04-21T22:00:00Z",
    }
    with sqlite3.connect(tmp_db) as conn:
        rows = parsers.parse_quote(conn, payload, meta)
        conn.commit()
    assert rows == 1

    with sqlite3.connect(tmp_db) as conn:
        r = conn.execute("SELECT symbol, current_price, run_id FROM quotes").fetchone()
    assert r == ("SOFI", 19.18, "run-abc")


@pytest.mark.unit
def test_parse_quote_batched(tmp_db: Path):
    connection.init_db()
    payload = {
        "count": 3,
        "quotes": [
            {"symbol": "VOO", "current_price": 649.94, "updated_at": "2026-04-21T22:00:00Z"},
            {"symbol": "QQQM", "current_price": 266.32, "updated_at": "2026-04-21T22:00:00Z"},
            {"symbol": "SPY", "current_price": 706.90, "updated_at": "2026-04-21T22:00:00Z"},
        ],
    }
    meta = {
        "run_id": "run-batched",
        "command": ["rh", "quote", "VOO", "QQQM", "SPY"],
        "created_at": "2026-04-21T22:00:00Z",
    }
    with sqlite3.connect(tmp_db) as conn:
        rows = parsers.parse_quote(conn, payload, meta)
        conn.commit()
    assert rows == 3

    with sqlite3.connect(tmp_db) as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
    assert cnt == 3


@pytest.mark.unit
def test_parse_quote_is_idempotent(tmp_db: Path):
    connection.init_db()
    payload = {"symbol": "SOFI", "current_price": 19.18, "updated_at": "2026-04-21T22:00:00Z"}
    meta = {"run_id": "r1", "command": ["rh", "quote", "SOFI"]}
    with sqlite3.connect(tmp_db) as conn:
        parsers.parse_quote(conn, payload, meta)
        parsers.parse_quote(conn, payload, meta)  # re-run
        conn.commit()
    with sqlite3.connect(tmp_db) as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
    assert cnt == 1


@pytest.mark.unit
def test_parse_quote_rejects_bad_shape(tmp_db: Path):
    connection.init_db()
    meta = {"run_id": "bad", "command": ["rh", "quote"]}
    with sqlite3.connect(tmp_db) as conn:
        with pytest.raises(parsers.ParseError):
            parsers.parse_quote(conn, {"some": "garbage"}, meta)


@pytest.mark.unit
def test_live_sync_writes_local_snapshot_activity_and_quotes(tmp_db: Path, monkeypatch):
    connection.init_db()

    snapshot_payload = {
        "accounts": [
            {
                "account_number": "597357623",
                "brokerage_account_type": "individual",
                "portfolio_value": 31000,
                "cash": 50,
                "buying_power": 75,
                "holdings": [
                    {
                        "symbol": "QQQM",
                        "shares": 0.1,
                        "avg_cost": 250,
                        "current_price": 260,
                        "total_equity": 26,
                        "total_return": 1,
                    }
                ],
            },
        ],
    }

    monkeypatch.setattr(
        "cfo.market_db.live_sync.rh_bridge.activity",
        lambda limit=50: {
            "count": 1,
            "orders": [
                {
                    "id": "oid-live-1",
                    "account_number": "597357623",
                    "symbol": "QQQM",
                    "side": "buy",
                    "state": "filled",
                    "quantity": 0.1,
                    "average_price": 250.0,
                    "total_value": 25.0,
                    "asset_class": "equity",
                    "created_at": "2026-04-22T21:00:00Z",
                    "updated_at": "2026-04-22T21:00:01Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "cfo.market_db.live_sync.price_log.default_watchlist",
        lambda: ["QQQM"],
    )
    monkeypatch.setattr(
        "cfo.market_db.live_sync.rh_bridge.quotes",
        lambda symbols: {
            "count": 1,
            "quotes": [
                {
                    "symbol": "QQQM",
                    "current_price": 260.0,
                    "last_price": 259.5,
                    "bid": 259.9,
                    "ask": 260.1,
                    "updated_at": "2026-04-22T21:00:02Z",
                }
            ],
        },
    )

    result = sync_live_market_data(snapshot_payload=snapshot_payload)
    assert result.account_rows == 2
    assert result.activity_rows == 1
    assert result.quote_rows == 1
    assert result.errors == []

    with sqlite3.connect(tmp_db) as conn:
        accounts = conn.execute("SELECT COUNT(*) FROM accounts_snapshot").fetchone()[0]
        holdings = conn.execute("SELECT COUNT(*) FROM holdings_snapshot").fetchone()[0]
        activity = conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
        quotes = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        local_runs = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE schedule_name IN ('local-live-account', 'local-live-activity', 'local-live-quotes')"
        ).fetchone()[0]
    assert accounts == 1
    assert holdings == 1
    assert activity == 1
    assert quotes == 1
    assert local_runs == 3


# ---------------------------------------------------------------------------
# Parser: indexes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_index(tmp_db: Path):
    connection.init_db()
    payload = [
        {
            "symbol": "VIX",
            "value": 19.50,
            "open": 19.18,
            "high": 20.85,
            "low": 18.75,
            "previous_close": 18.87,
            "updated_at": "2026-04-21T21:57:21Z",
            "uuid": "uuid-vix",
        },
        {
            "symbol": "SPX",
            "value": 7064.01,
            "high_52_weeks": 7147.52,
            "updated_at": "2026-04-21T21:57:21Z",
        },
    ]
    meta = {"run_id": "idx-1", "command": ["rh", "index", "VIX", "SPX"]}
    with sqlite3.connect(tmp_db) as conn:
        rows = parsers.parse_index(conn, payload, meta)
        conn.commit()
    assert rows == 2


# ---------------------------------------------------------------------------
# Parser: option chain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_option_chain(tmp_db: Path):
    connection.init_db()
    payload = {
        "symbol": "SOFI",
        "expiration_date": "2026-05-22",
        "option_type": "put",
        "count": 2,
        "options": [
            {
                "instrument_id": "opt-17",
                "strike": 17.0,
                "type": "put",
                "bid": 0.73,
                "ask": 0.80,
                "mark": 0.77,
                "delta": -0.276,
                "iv": 0.738,
                "open_interest": 1063,
                "volume": 50,
                "chance_of_profit_short": 0.725,
            },
            {
                "instrument_id": "opt-16",
                "strike": 16.0,
                "type": "put",
                "mark": 0.48,
                "delta": -0.192,
                "iv": 0.746,
            },
        ],
    }
    meta = {
        "run_id": "opt-run",
        "command": ["rh", "option", "chain", "SOFI", "--exp", "2026-05-22"],
        "finished_at": "2026-04-21T20:30:00Z",
    }
    with sqlite3.connect(tmp_db) as conn:
        rows = parsers.parse_option_chain(conn, payload, meta)
        conn.commit()
    assert rows == 2

    with sqlite3.connect(tmp_db) as conn:
        r = conn.execute(
            "SELECT symbol, expiration, strike, type, mark FROM option_chain WHERE instrument_id='opt-17'"
        ).fetchone()
    assert r == ("SOFI", "2026-05-22", 17.0, "put", 0.77)


# ---------------------------------------------------------------------------
# Parser: news
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_news(tmp_db: Path):
    connection.init_db()
    payload = {
        "count": 2,
        "news": [
            {
                "url": "https://example.com/a",
                "title": "Tesla ups robotaxi",
                "source": "TipRanks",
                "published_at": "2026-04-21T19:11:02Z",
            },
            {
                "url": "https://example.com/b",
                "title": "Tesla stock slips",
                "source": "Reuters",
                "published_at": "2026-04-21T17:07:33Z",
            },
        ],
    }
    meta = {
        "run_id": "news-1",
        "command": ["rh", "symbol", "news", "TSLA", "--format", "json"],
    }
    with sqlite3.connect(tmp_db) as conn:
        rows = parsers.parse_news(conn, payload, meta)
        conn.commit()
    assert rows == 2

    with sqlite3.connect(tmp_db) as conn:
        r = conn.execute("SELECT symbol FROM news LIMIT 1").fetchone()
    assert r[0] == "TSLA"  # extracted from argv, not payload


@pytest.mark.unit
def test_parse_news_idempotent_on_same_url(tmp_db: Path):
    connection.init_db()
    payload = {
        "news": [
            {"url": "https://x/1", "title": "t1", "published_at": "2026-04-21T00:00:00Z"}
        ]
    }
    meta = {"run_id": "r", "command": ["rh", "symbol", "news", "SOFI"]}
    with sqlite3.connect(tmp_db) as conn:
        parsers.parse_news(conn, payload, meta)
        parsers.parse_news(conn, payload, meta)  # second time — should not duplicate
        conn.commit()
    with sqlite3.connect(tmp_db) as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    assert cnt == 1


# ---------------------------------------------------------------------------
# Parser: scan
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_scan_up(tmp_db: Path):
    connection.init_db()
    payload = {
        "count": 2,
        "rows": [
            {
                "symbol": "FFAI",
                "direction": "up",
                "change_1d_pct": 75.76,
                "price": "$0.5039",
                "volume": "582.46M",
                "market_cap": "132.87M",
                "instrument_id": "uid-ffai",
                "name": "Faraday Future",
            },
            {
                "symbol": "ELSE",
                "direction": "up",
                "change_1d_pct": 72.65,
                "price": "$7.64",
            },
        ],
    }
    meta = {
        "run_id": "scan-1",
        "command": ["rh", "scan", "--min-change", "10"],
        "finished_at": "2026-04-21T20:27:00Z",
    }
    with sqlite3.connect(tmp_db) as conn:
        rows = parsers.parse_scan(conn, payload, meta)
        conn.commit()
    assert rows == 2

    with sqlite3.connect(tmp_db) as conn:
        r = conn.execute(
            "SELECT direction FROM movers_scan WHERE symbol='FFAI'"
        ).fetchone()
    assert r[0] == "up"


@pytest.mark.unit
def test_parse_scan_infers_down_from_argv(tmp_db: Path):
    connection.init_db()
    payload = {
        "rows": [
            {"symbol": "HNORY", "change_1d_pct": -37.93},
        ]
    }
    meta = {
        "run_id": "scan-dn",
        "command": ["rh", "scan", "--max-change", "-10"],
    }
    with sqlite3.connect(tmp_db) as conn:
        parsers.parse_scan(conn, payload, meta)
        conn.commit()
    with sqlite3.connect(tmp_db) as conn:
        d = conn.execute("SELECT direction FROM movers_scan").fetchone()[0]
    assert d == "down"
