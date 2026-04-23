"""SQLite schema for the market database.

Versioned via ``schema_version`` table. When you change a table, bump
``CURRENT_VERSION`` and add a migration entry in ``MIGRATIONS``.

All timestamps stored as TEXT in UTC ISO 8601 (e.g. ``2026-04-21T21:05:00Z``);
SQLite has no native TIMESTAMP type, use ``datetime(ts)`` at query time.
"""
from __future__ import annotations

CURRENT_VERSION = 1


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT
);
"""

SYNC_STATE_DDL = """
CREATE TABLE IF NOT EXISTS sync_state (
    schedule_id TEXT PRIMARY KEY,
    schedule_name TEXT,
    last_run_id TEXT,
    last_run_created_at TEXT,
    last_sync_at TEXT,
    runs_processed_total INTEGER NOT NULL DEFAULT 0,
    parser_override TEXT,
    notes TEXT
);
"""

INGEST_LOG_DDL = """
CREATE TABLE IF NOT EXISTS ingest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_started_at TEXT NOT NULL,
    sync_finished_at TEXT,
    schedule_id TEXT,
    schedule_name TEXT,
    runs_fetched INTEGER NOT NULL DEFAULT 0,
    runs_inserted INTEGER NOT NULL DEFAULT 0,
    runs_skipped INTEGER NOT NULL DEFAULT 0,
    rows_written INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT
);
"""

RUNS_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    schedule_id TEXT,
    schedule_name TEXT,
    status TEXT NOT NULL,
    exit_code INTEGER,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    command_json TEXT,
    parser TEXT,
    rows_written INTEGER DEFAULT 0,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_schedule_created
    ON runs(schedule_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_parser_created
    ON runs(parser, created_at);
"""

UNKNOWN_PAYLOADS_DDL = """
CREATE TABLE IF NOT EXISTS unknown_payloads (
    run_id TEXT PRIMARY KEY,
    schedule_id TEXT,
    schedule_name TEXT,
    command_json TEXT,
    payload_json TEXT,
    ingested_at TEXT NOT NULL,
    notes TEXT
);
"""

QUOTES_DDL = """
CREATE TABLE IF NOT EXISTS quotes (
    symbol TEXT NOT NULL,
    ts TEXT NOT NULL,
    current_price REAL,
    last_price REAL,
    extended_hours_price REAL,
    bid REAL,
    ask REAL,
    previous_close REAL,
    previous_close_date TEXT,
    day_change REAL,
    day_change_pct REAL,
    volume REAL,
    average_volume REAL,
    open REAL,
    high REAL,
    low REAL,
    high_52_weeks REAL,
    low_52_weeks REAL,
    market_cap REAL,
    pe_ratio REAL,
    dividend_yield REAL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_quotes_symbol_ts
    ON quotes(symbol, ts);
"""

INDEXES_DDL = """
CREATE TABLE IF NOT EXISTS indexes (
    symbol TEXT NOT NULL,
    ts TEXT NOT NULL,
    value REAL,
    open REAL,
    high REAL,
    low REAL,
    previous_close REAL,
    previous_close_date TEXT,
    high_52_weeks REAL,
    low_52_weeks REAL,
    pe_ratio REAL,
    market_cap REAL,
    venue_timestamp TEXT,
    state TEXT,
    uuid TEXT,
    run_id TEXT NOT NULL,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_indexes_symbol_ts
    ON indexes(symbol, ts);
"""

OPTION_CHAIN_DDL = """
CREATE TABLE IF NOT EXISTS option_chain (
    instrument_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    expiration TEXT NOT NULL,
    strike REAL NOT NULL,
    type TEXT NOT NULL,
    ts TEXT NOT NULL,
    bid REAL,
    ask REAL,
    last REAL,
    mark REAL,
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,
    rho REAL,
    iv REAL,
    open_interest INTEGER,
    volume INTEGER,
    chance_of_profit_long REAL,
    chance_of_profit_short REAL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (instrument_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_option_symbol_exp_strike_type_ts
    ON option_chain(symbol, expiration, strike, type, ts);
CREATE INDEX IF NOT EXISTS idx_option_ts
    ON option_chain(ts);
"""

NEWS_DDL = """
CREATE TABLE IF NOT EXISTS news (
    symbol TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    source TEXT,
    summary TEXT,
    preview_image_url TEXT,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (symbol, url)
);
CREATE INDEX IF NOT EXISTS idx_news_symbol_published
    ON news(symbol, published_at);
"""

MOVERS_SCAN_DDL = """
CREATE TABLE IF NOT EXISTS movers_scan (
    ts TEXT NOT NULL,
    direction TEXT NOT NULL,
    symbol TEXT NOT NULL,
    change_pct REAL,
    price TEXT,
    volume TEXT,
    market_cap TEXT,
    instrument_id TEXT,
    name TEXT,
    run_id TEXT NOT NULL,
    PRIMARY KEY (ts, direction, symbol)
);
CREATE INDEX IF NOT EXISTS idx_movers_scan_symbol_ts
    ON movers_scan(symbol, ts);
"""

SP500_MOVERS_DDL = """
CREATE TABLE IF NOT EXISTS sp500_movers (
    ts TEXT NOT NULL,
    direction TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price_movement_pct REAL,
    description TEXT,
    updated_at TEXT,
    run_id TEXT NOT NULL,
    PRIMARY KEY (ts, direction, symbol)
);
CREATE INDEX IF NOT EXISTS idx_sp500_movers_ts
    ON sp500_movers(ts, direction);
"""

ACCOUNTS_SNAPSHOT_DDL = """
CREATE TABLE IF NOT EXISTS accounts_snapshot (
    ts TEXT NOT NULL,
    account_number TEXT NOT NULL,
    account_type TEXT,
    cash REAL,
    equity REAL,
    total_portfolio REAL,
    buying_power REAL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (ts, account_number)
);
"""

HOLDINGS_SNAPSHOT_DDL = """
CREATE TABLE IF NOT EXISTS holdings_snapshot (
    ts TEXT NOT NULL,
    account_number TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity REAL,
    average_cost REAL,
    market_value REAL,
    total_return REAL,
    total_return_pct REAL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (ts, account_number, symbol)
);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol_ts
    ON holdings_snapshot(symbol, ts);
"""

ACTIVITY_DDL = """
CREATE TABLE IF NOT EXISTS activity (
    order_id TEXT PRIMARY KEY,
    created_at TEXT,
    updated_at TEXT,
    symbol TEXT,
    side TEXT,
    state TEXT,
    quantity REAL,
    price REAL,
    total_value REAL,
    asset_type TEXT,
    account_number TEXT,
    first_seen_run_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_symbol_created
    ON activity(symbol, created_at);
"""

DIVIDENDS_DDL = """
CREATE TABLE IF NOT EXISTS dividends (
    dividend_id TEXT PRIMARY KEY,
    symbol TEXT,
    amount REAL,
    rate REAL,
    position REAL,
    state TEXT,
    record_date TEXT,
    payable_date TEXT,
    paid_at TEXT,
    account_number TEXT,
    run_id TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dividends_symbol_paid
    ON dividends(symbol, paid_at);
"""

TRANSFERS_DDL = """
CREATE TABLE IF NOT EXISTS transfers (
    transfer_id TEXT PRIMARY KEY,
    created_at TEXT,
    updated_at TEXT,
    direction TEXT,
    amount REAL,
    state TEXT,
    account_number TEXT,
    bank_description TEXT,
    run_id TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transfers_created
    ON transfers(created_at);
"""


ALL_DDL = [
    SCHEMA_VERSION_DDL,
    SYNC_STATE_DDL,
    INGEST_LOG_DDL,
    RUNS_DDL,
    UNKNOWN_PAYLOADS_DDL,
    QUOTES_DDL,
    INDEXES_DDL,
    OPTION_CHAIN_DDL,
    NEWS_DDL,
    MOVERS_SCAN_DDL,
    SP500_MOVERS_DDL,
    ACCOUNTS_SNAPSHOT_DDL,
    HOLDINGS_SNAPSHOT_DDL,
    ACTIVITY_DDL,
    DIVIDENDS_DDL,
    TRANSFERS_DDL,
]


# ---------------------------------------------------------------------------
# Migrations (append to this list for any schema evolution)
# ---------------------------------------------------------------------------

MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "initial schema",
        ALL_DDL,
    ),
]
