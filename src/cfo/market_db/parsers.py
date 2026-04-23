"""Parsers — payload JSON → rows in specific tables.

Each parser returns a tuple ``(rows_written, errors)``. Parsers are
idempotent: re-running on the same payload MUST NOT produce duplicate
rows (enforced by UPSERT ``INSERT ... ON CONFLICT DO UPDATE``).

Parsers are invoked by name (string); see ``sync.py`` for the registry
wiring. New parsers should be added here and registered in
``dispatch.PARSER_REGISTRY``.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class ParseError(ValueError):
    """Raised when a payload violates its expected shape."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(v: Any) -> float | None:
    """Tolerant float coercion: returns None for ``None``/``""``/bad data."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _s(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)


def _ts_fallback(payload: Mapping[str, Any], meta: Mapping[str, Any]) -> str:
    """Best-effort timestamp for rows that lack their own ts field.

    Prefers ``payload["updated_at"]`` → meta["finished_at"] → meta["created_at"]
    → current UTC.
    """
    for candidate in (
        payload.get("updated_at"),
        meta.get("finished_at"),
        meta.get("created_at"),
    ):
        if candidate:
            return str(candidate)
    return _utc_now()


# ---------------------------------------------------------------------------
# Quote parser (handles both single-symbol and batched payloads)
# ---------------------------------------------------------------------------


def _upsert_quote_row(conn: sqlite3.Connection, q: Mapping[str, Any], run_id: str, fallback_ts: str) -> int:
    if "symbol" not in q:
        return 0
    ts = q.get("updated_at") or fallback_ts
    conn.execute(
        """
        INSERT INTO quotes(
            symbol, ts, current_price, last_price, extended_hours_price,
            bid, ask, previous_close, previous_close_date, day_change,
            day_change_pct, volume, average_volume, open, high, low,
            high_52_weeks, low_52_weeks, market_cap, pe_ratio,
            dividend_yield, run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(symbol, ts) DO UPDATE SET
            current_price=excluded.current_price,
            last_price=excluded.last_price,
            extended_hours_price=excluded.extended_hours_price,
            bid=excluded.bid,
            ask=excluded.ask,
            previous_close=excluded.previous_close,
            day_change=excluded.day_change,
            day_change_pct=excluded.day_change_pct,
            volume=excluded.volume,
            run_id=excluded.run_id
        """,
        (
            _s(q["symbol"]),
            _s(ts),
            _f(q.get("current_price")),
            _f(q.get("last_price")),
            _f(q.get("extended_hours_price")),
            _f(q.get("bid")),
            _f(q.get("ask")),
            _f(q.get("previous_close")),
            _s(q.get("previous_close_date")),
            _f(q.get("day_change")),
            _f(q.get("day_change_pct")),
            _f(q.get("volume")),
            _f(q.get("average_volume")),
            _f(q.get("open")),
            _f(q.get("high")),
            _f(q.get("low")),
            _f(q.get("high_52_weeks")),
            _f(q.get("low_52_weeks")),
            _f(q.get("market_cap")),
            _f(q.get("pe_ratio")),
            _f(q.get("dividend_yield")),
            run_id,
        ),
    )
    return 1


def parse_quote(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    fallback = _ts_fallback(payload if isinstance(payload, Mapping) else {}, meta)
    rows = 0
    # Batched: {"count": N, "quotes": [...]}
    if isinstance(payload, Mapping) and "quotes" in payload and isinstance(payload["quotes"], list):
        for q in payload["quotes"]:
            if isinstance(q, Mapping):
                rows += _upsert_quote_row(conn, q, run_id, fallback)
        return rows
    # Single: flat dict
    if isinstance(payload, Mapping) and "symbol" in payload:
        rows += _upsert_quote_row(conn, payload, run_id, fallback)
        return rows
    raise ParseError("parse_quote: unexpected payload shape")


# ---------------------------------------------------------------------------
# Index parser (always list-shaped; rh index always returns an array)
# ---------------------------------------------------------------------------


def parse_index(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    fallback = _ts_fallback({}, meta)
    if not isinstance(payload, list):
        raise ParseError("parse_index: expected a list payload")
    rows = 0
    for entry in payload:
        if not isinstance(entry, Mapping):
            continue
        sym = entry.get("symbol")
        if not sym:
            continue
        ts = entry.get("updated_at") or entry.get("venue_timestamp") or fallback
        conn.execute(
            """
            INSERT INTO indexes(
                symbol, ts, value, open, high, low, previous_close,
                previous_close_date, high_52_weeks, low_52_weeks,
                pe_ratio, market_cap, venue_timestamp, state, uuid, run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol, ts) DO UPDATE SET
                value=excluded.value,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                previous_close=excluded.previous_close,
                run_id=excluded.run_id
            """,
            (
                _s(sym),
                _s(ts),
                _f(entry.get("value")),
                _f(entry.get("open")),
                _f(entry.get("high")),
                _f(entry.get("low")),
                _f(entry.get("previous_close")),
                _s(entry.get("previous_close_date")),
                _f(entry.get("high_52_weeks")),
                _f(entry.get("low_52_weeks")),
                _f(entry.get("pe_ratio")),
                _f(entry.get("market_cap")),
                _s(entry.get("venue_timestamp")),
                _s(entry.get("state")),
                _s(entry.get("uuid")),
                run_id,
            ),
        )
        rows += 1
    return rows


# ---------------------------------------------------------------------------
# Option chain parser — each option row keyed by (instrument_id, ts)
# ---------------------------------------------------------------------------


def parse_option_chain(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    fallback = _ts_fallback({}, meta)
    if not isinstance(payload, Mapping):
        raise ParseError("parse_option_chain: expected a dict payload")
    symbol = payload.get("symbol")
    expiration = payload.get("expiration_date")
    options = payload.get("options")
    if not symbol or not expiration or not isinstance(options, list):
        raise ParseError("parse_option_chain: missing symbol/expiration_date/options")
    rows = 0
    for o in options:
        if not isinstance(o, Mapping):
            continue
        inst = o.get("instrument_id")
        if not inst:
            continue
        conn.execute(
            """
            INSERT INTO option_chain(
                instrument_id, symbol, expiration, strike, type, ts,
                bid, ask, last, mark, delta, gamma, theta, vega, rho,
                iv, open_interest, volume, chance_of_profit_long,
                chance_of_profit_short, run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(instrument_id, ts) DO UPDATE SET
                bid=excluded.bid,
                ask=excluded.ask,
                last=excluded.last,
                mark=excluded.mark,
                delta=excluded.delta,
                gamma=excluded.gamma,
                theta=excluded.theta,
                vega=excluded.vega,
                rho=excluded.rho,
                iv=excluded.iv,
                open_interest=excluded.open_interest,
                volume=excluded.volume,
                run_id=excluded.run_id
            """,
            (
                _s(inst),
                _s(symbol),
                _s(expiration),
                _f(o.get("strike")),
                _s(o.get("type")),
                _s(fallback),
                _f(o.get("bid")),
                _f(o.get("ask")),
                _f(o.get("last")),
                _f(o.get("mark")),
                _f(o.get("delta")),
                _f(o.get("gamma")),
                _f(o.get("theta")),
                _f(o.get("vega")),
                _f(o.get("rho")),
                _f(o.get("iv")),
                _i(o.get("open_interest")),
                _i(o.get("volume")),
                _f(o.get("chance_of_profit_long")),
                _f(o.get("chance_of_profit_short")),
                run_id,
            ),
        )
        rows += 1
    return rows


# ---------------------------------------------------------------------------
# News parser
# ---------------------------------------------------------------------------


def parse_news(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    seen_at = _utc_now()
    # rh symbol news --format json returns {"count": N, "news": [...]}
    # but the symbol itself is in the command argv, not the payload body.
    command = meta.get("command") or []
    symbol = None
    # argv: ['rh', 'symbol', 'news', 'SOFI', ...]
    for idx, token in enumerate(command):
        if token == "news" and idx + 1 < len(command):
            cand = command[idx + 1]
            if not cand.startswith("-"):
                symbol = cand
                break
    if not isinstance(payload, Mapping) or "news" not in payload:
        raise ParseError("parse_news: expected dict with 'news' list")
    items = payload["news"]
    if not isinstance(items, list):
        raise ParseError("parse_news: 'news' should be a list")
    rows = 0
    for n in items:
        if not isinstance(n, Mapping):
            continue
        url = n.get("url")
        if not url:
            continue
        conn.execute(
            """
            INSERT INTO news(
                symbol, url, title, source, summary, preview_image_url,
                published_at, first_seen_at, run_id
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol, url) DO NOTHING
            """,
            (
                _s(symbol or "UNKNOWN"),
                _s(url),
                _s(n.get("title")),
                _s(n.get("source")),
                _s(n.get("summary")),
                _s(n.get("preview_image_url")),
                _s(n.get("published_at")),
                seen_at,
                run_id,
            ),
        )
        rows += 1
    return rows


# ---------------------------------------------------------------------------
# Scan parser (full-market Bonfire screener)
# ---------------------------------------------------------------------------


def parse_scan(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    ts = _ts_fallback({}, meta)
    if not isinstance(payload, Mapping) or "rows" not in payload:
        raise ParseError("parse_scan: expected dict with 'rows' list")
    # rh scan --min-change N → direction always "up" (positive)
    # rh scan --max-change -N → direction always "down" (negative)
    command = meta.get("command") or []
    direction_hint = "up"
    for idx, token in enumerate(command):
        if token == "--max-change" and idx + 1 < len(command):
            try:
                if float(command[idx + 1]) < 0:
                    direction_hint = "down"
            except (ValueError, IndexError):
                pass
    rows = 0
    for r in payload["rows"]:
        if not isinstance(r, Mapping):
            continue
        sym = r.get("symbol")
        if not sym:
            continue
        dir_field = r.get("direction") or direction_hint
        conn.execute(
            """
            INSERT INTO movers_scan(
                ts, direction, symbol, change_pct, price, volume,
                market_cap, instrument_id, name, run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ts, direction, symbol) DO UPDATE SET
                change_pct=excluded.change_pct,
                price=excluded.price,
                volume=excluded.volume,
                market_cap=excluded.market_cap,
                run_id=excluded.run_id
            """,
            (
                _s(ts),
                _s(dir_field),
                _s(sym),
                _f(r.get("change_1d_pct")),
                _s(r.get("price")),
                _s(r.get("volume")),
                _s(r.get("market_cap")),
                _s(r.get("instrument_id")),
                _s(r.get("name")),
                run_id,
            ),
        )
        rows += 1
    return rows


# ---------------------------------------------------------------------------
# S&P 500 movers (rh movers --direction up|down)
# ---------------------------------------------------------------------------


def parse_sp500_movers(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    ts = _ts_fallback({}, meta)
    if not isinstance(payload, Mapping) or "movers" not in payload:
        raise ParseError("parse_sp500_movers: expected 'movers' key")
    direction = _s(payload.get("direction") or "up")
    rows = 0
    for m in payload["movers"]:
        if not isinstance(m, Mapping):
            continue
        sym = m.get("symbol")
        if not sym:
            continue
        conn.execute(
            """
            INSERT INTO sp500_movers(
                ts, direction, symbol, price_movement_pct,
                description, updated_at, run_id
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(ts, direction, symbol) DO UPDATE SET
                price_movement_pct=excluded.price_movement_pct,
                description=excluded.description,
                run_id=excluded.run_id
            """,
            (
                _s(ts),
                direction,
                _s(sym),
                _f(m.get("price_movement_pct")),
                _s(m.get("description")),
                _s(m.get("updated_at")),
                run_id,
            ),
        )
        rows += 1
    return rows


# ---------------------------------------------------------------------------
# Account snapshot (rh account snapshot)
# ---------------------------------------------------------------------------


def parse_account_snapshot(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    """Parse ``rh account snapshot`` payload.

    Payload shape (discovered by introspection):
      accounts[*].account_number, account_type, brokerage_account_type,
                  buying_power, cash, nickname, portfolio_value,
                  holdings[*].symbol, shares, avg_cost, current_price,
                               total_equity, total_return
    """
    run_id = str(meta["run_id"])
    ts = _ts_fallback({}, meta)
    if not isinstance(payload, Mapping) or "accounts" not in payload:
        raise ParseError("parse_account_snapshot: expected 'accounts' list")
    rows = 0
    for a in payload["accounts"]:
        if not isinstance(a, Mapping):
            continue
        acct_no = a.get("account_number")
        if not acct_no:
            continue
        conn.execute(
            """
            INSERT INTO accounts_snapshot(
                ts, account_number, account_type, cash, equity,
                total_portfolio, buying_power, run_id
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(ts, account_number) DO UPDATE SET
                cash=excluded.cash,
                equity=excluded.equity,
                total_portfolio=excluded.total_portfolio,
                buying_power=excluded.buying_power,
                run_id=excluded.run_id
            """,
            (
                _s(ts),
                _s(acct_no),
                _s(a.get("account_type") or a.get("brokerage_account_type")),
                _f(a.get("cash")),
                _f(a.get("equity")),
                _f(a.get("portfolio_value") or a.get("total_portfolio") or a.get("total")),
                _f(a.get("buying_power")),
                run_id,
            ),
        )
        rows += 1
        for h in a.get("holdings", []) or []:
            if not isinstance(h, Mapping):
                continue
            sym = h.get("symbol")
            if not sym:
                continue
            # Compute total_return_pct if not given: total_return / (avg_cost * shares).
            avg_cost = _f(h.get("avg_cost") or h.get("average_cost") or h.get("cost_basis"))
            shares = _f(h.get("shares") or h.get("quantity"))
            total_return = _f(h.get("total_return"))
            total_return_pct = _f(h.get("total_return_pct"))
            if total_return_pct is None and total_return is not None and avg_cost and shares:
                basis = avg_cost * shares
                if basis:
                    total_return_pct = total_return / basis * 100
            conn.execute(
                """
                INSERT INTO holdings_snapshot(
                    ts, account_number, symbol, quantity, average_cost,
                    market_value, total_return, total_return_pct, run_id
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ts, account_number, symbol) DO UPDATE SET
                    quantity=excluded.quantity,
                    average_cost=excluded.average_cost,
                    market_value=excluded.market_value,
                    total_return=excluded.total_return,
                    total_return_pct=excluded.total_return_pct,
                    run_id=excluded.run_id
                """,
                (
                    _s(ts),
                    _s(acct_no),
                    _s(sym),
                    shares,
                    avg_cost,
                    _f(h.get("total_equity") or h.get("market_value") or h.get("equity")),
                    total_return,
                    total_return_pct,
                    run_id,
                ),
            )
            rows += 1
    return rows


# ---------------------------------------------------------------------------
# Activity (rh activity) — orders
# ---------------------------------------------------------------------------


def parse_activity(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    """Parse ``rh activity`` payload.

    Order field names discovered: id, symbol, side, state, quantity,
    average_price, total_value, asset_class, order_type, account_number,
    created_at, updated_at.
    """
    run_id = str(meta["run_id"])
    seen_at = _utc_now()
    if not isinstance(payload, Mapping) or "orders" not in payload:
        raise ParseError("parse_activity: expected 'orders' list")
    rows = 0
    for o in payload["orders"]:
        if not isinstance(o, Mapping):
            continue
        oid = o.get("id") or o.get("order_id")
        if not oid:
            continue
        conn.execute(
            """
            INSERT INTO activity(
                order_id, created_at, updated_at, symbol, side, state,
                quantity, price, total_value, asset_type, account_number,
                first_seen_run_id, first_seen_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(order_id) DO UPDATE SET
                state=excluded.state,
                updated_at=excluded.updated_at,
                quantity=excluded.quantity,
                price=excluded.price,
                total_value=excluded.total_value
            """,
            (
                _s(oid),
                _s(o.get("created_at")),
                _s(o.get("updated_at")),
                _s(o.get("symbol")),
                _s(o.get("side")),
                _s(o.get("state")),
                _f(o.get("quantity")),
                _f(o.get("average_price") or o.get("price")),
                _f(o.get("total_value")),
                _s(o.get("asset_class") or o.get("asset_type")),
                _s(o.get("account_number") or o.get("account")),
                run_id,
                seen_at,
            ),
        )
        rows += 1
    return rows


# ---------------------------------------------------------------------------
# Dividends / Transfers
# ---------------------------------------------------------------------------


def parse_dividends(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    ingested_at = _utc_now()
    if not isinstance(payload, Mapping):
        raise ParseError("parse_dividends: expected dict payload")
    items = payload.get("dividends") or payload.get("results") or []
    if not isinstance(items, list):
        raise ParseError("parse_dividends: dividends must be a list")
    rows = 0
    for d in items:
        if not isinstance(d, Mapping):
            continue
        div_id = d.get("id") or d.get("dividend_id")
        if not div_id:
            # Fallback: synthesize from symbol + payable_date
            div_id = f"{d.get('symbol','?')}:{d.get('payable_date','?')}:{d.get('amount','?')}"
        conn.execute(
            """
            INSERT INTO dividends(
                dividend_id, symbol, amount, rate, position, state,
                record_date, payable_date, paid_at, account_number,
                run_id, ingested_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(dividend_id) DO UPDATE SET
                state=excluded.state,
                amount=excluded.amount,
                paid_at=excluded.paid_at
            """,
            (
                _s(div_id),
                _s(d.get("symbol")),
                _f(d.get("amount")),
                _f(d.get("rate")),
                _f(d.get("position")),
                _s(d.get("state")),
                _s(d.get("record_date")),
                _s(d.get("payable_date")),
                _s(d.get("paid_at")),
                _s(d.get("account_number") or d.get("account")),
                run_id,
                ingested_at,
            ),
        )
        rows += 1
    return rows


def parse_transfers(conn: sqlite3.Connection, payload: Any, meta: Mapping[str, Any]) -> int:
    run_id = str(meta["run_id"])
    ingested_at = _utc_now()
    if not isinstance(payload, Mapping):
        raise ParseError("parse_transfers: expected dict payload")
    items = payload.get("transfers") or payload.get("results") or []
    if not isinstance(items, list):
        raise ParseError("parse_transfers: transfers must be a list")
    rows = 0
    for t in items:
        if not isinstance(t, Mapping):
            continue
        tid = t.get("id") or t.get("transfer_id")
        if not tid:
            tid = f"{t.get('created_at','?')}:{t.get('amount','?')}:{t.get('direction','?')}"
        conn.execute(
            """
            INSERT INTO transfers(
                transfer_id, created_at, updated_at, direction, amount,
                state, account_number, bank_description, run_id, ingested_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(transfer_id) DO UPDATE SET
                state=excluded.state,
                updated_at=excluded.updated_at
            """,
            (
                _s(tid),
                _s(t.get("created_at")),
                _s(t.get("updated_at")),
                _s(t.get("direction")),
                _f(t.get("amount")),
                _s(t.get("state")),
                _s(t.get("account_number") or t.get("account")),
                _s(t.get("bank_description") or t.get("bank")),
                run_id,
                ingested_at,
            ),
        )
        rows += 1
    return rows


# ---------------------------------------------------------------------------
# Stubs for less-critical parsers (currently parse nothing; data falls
# through to unknown_payloads until we wire a real implementation).
# ---------------------------------------------------------------------------


def _stub(_conn: sqlite3.Connection, _payload: Any, _meta: Mapping[str, Any]) -> int:
    return 0


# Alias table: unsupported parsers. dispatch returns their name but
# PARSER_IMPLEMENTATIONS routes to _stub, which means the run will be
# recorded in `runs` with rows_written=0. Keep it explicit rather than
# silently dropping to unknown_payloads, so auditing is clearer.
parse_option_positions = _stub
parse_option_expirations = _stub
parse_option_history = _stub
parse_earnings = _stub
parse_ratings = _stub
parse_similar = _stub
parse_tags = _stub
parse_splits = _stub
parse_symbol_search = _stub
parse_account_list = _stub
parse_account_show = _stub
parse_market_status = _stub
parse_margin = _stub
parse_pdt = _stub
parse_gold = _stub
parse_bars = _stub
parse_crypto_quote = _stub
parse_crypto_holdings = _stub
parse_watchlist_list = _stub
parse_watchlist_show = _stub
parse_notifications = _stub
parse_documents = _stub
parse_order_detail = _stub


# Exported map: parser_name → callable
PARSER_IMPLEMENTATIONS: dict[str, Any] = {
    "parse_quote": parse_quote,
    "parse_index": parse_index,
    "parse_option_chain": parse_option_chain,
    "parse_news": parse_news,
    "parse_scan": parse_scan,
    "parse_sp500_movers": parse_sp500_movers,
    "parse_account_snapshot": parse_account_snapshot,
    "parse_activity": parse_activity,
    "parse_dividends": parse_dividends,
    "parse_transfers": parse_transfers,
    "parse_option_positions": parse_option_positions,
    "parse_option_expirations": parse_option_expirations,
    "parse_option_history": parse_option_history,
    "parse_earnings": parse_earnings,
    "parse_ratings": parse_ratings,
    "parse_similar": parse_similar,
    "parse_tags": parse_tags,
    "parse_splits": parse_splits,
    "parse_symbol_search": parse_symbol_search,
    "parse_account_list": parse_account_list,
    "parse_account_show": parse_account_show,
    "parse_market_status": parse_market_status,
    "parse_margin": parse_margin,
    "parse_pdt": parse_pdt,
    "parse_gold": parse_gold,
    "parse_bars": parse_bars,
    "parse_crypto_quote": parse_crypto_quote,
    "parse_crypto_holdings": parse_crypto_holdings,
    "parse_watchlist_list": parse_watchlist_list,
    "parse_watchlist_show": parse_watchlist_show,
    "parse_notifications": parse_notifications,
    "parse_documents": parse_documents,
    "parse_order_detail": parse_order_detail,
}
