"""Live local ingest into market.db.

This complements the rh-server schedule pipeline: `cfo sync` can pull the
latest local Robinhood view (accounts, activity, tracked quotes) and write it
directly into market.db without waiting for remote schedules to run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from cfo.core import price_log, rh_bridge
from cfo.market_db import parsers
from cfo.market_db.connection import connect


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class LiveSyncResult:
    account_rows: int = 0
    activity_rows: int = 0
    quote_rows: int = 0
    errors: list[str] = field(default_factory=list)


def _new_run_id(kind: str) -> str:
    return f"local-{kind}-{uuid4()}"


def _insert_runs_row(
    *,
    conn,
    run_id: str,
    schedule_name: str,
    parser_name: str,
    command: list[str],
    rows_written: int,
    started_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO runs(
            run_id, schedule_id, schedule_name, status, exit_code,
            created_at, started_at, finished_at, command_json, parser,
            rows_written, ingested_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET
            status=excluded.status,
            rows_written=excluded.rows_written,
            parser=excluded.parser
        """,
        (
            run_id,
            None,
            schedule_name,
            "succeeded",
            0,
            started_at,
            started_at,
            started_at,
            json.dumps(command),
            parser_name,
            rows_written,
            _utc_now(),
        ),
    )


def _ingest(
    *,
    conn,
    kind: str,
    schedule_name: str,
    parser_name: str,
    command: list[str],
    payload: Mapping[str, Any] | list[Any],
    created_at: str | None = None,
) -> int:
    run_id = _new_run_id(kind)
    ts = created_at or _utc_now()
    meta = {
        "run_id": run_id,
        "command": command,
        "created_at": ts,
        "finished_at": ts,
    }
    parser = parsers.PARSER_IMPLEMENTATIONS[parser_name]
    rows = parser(conn, payload, meta)
    _insert_runs_row(
        conn=conn,
        run_id=run_id,
        schedule_name=schedule_name,
        parser_name=parser_name,
        command=command,
        rows_written=rows,
        started_at=ts,
    )
    return rows


def sync_live_market_data(
    *,
    snapshot_payload: Mapping[str, Any] | None = None,
    activity_limit: int = 50,
    quote_symbols: list[str] | None = None,
) -> LiveSyncResult:
    result = LiveSyncResult()

    if quote_symbols is None:
        quote_symbols = price_log.default_watchlist()
    quote_symbols = sorted({str(sym).upper() for sym in quote_symbols if str(sym).strip()})

    with connect() as conn:
        if snapshot_payload is None:
            try:
                snapshot_payload = rh_bridge.snapshot()
            except RuntimeError as exc:
                result.errors.append(f"snapshot failed: {exc}")
                snapshot_payload = None
        if snapshot_payload is not None:
            try:
                result.account_rows = _ingest(
                    conn=conn,
                    kind="account",
                    schedule_name="local-live-account",
                    parser_name="parse_account_snapshot",
                    command=["rh", "account", "snapshot", "--format", "json"],
                    payload=snapshot_payload,
                )
            except Exception as exc:  # noqa: BLE001 - best effort
                result.errors.append(f"account snapshot ingest failed: {exc}")

        try:
            activity_payload = rh_bridge.activity(limit=activity_limit)
            result.activity_rows = _ingest(
                conn=conn,
                kind="activity",
                schedule_name="local-live-activity",
                parser_name="parse_activity",
                command=["rh", "activity", "--limit", str(activity_limit), "--format", "json"],
                payload=activity_payload,
            )
        except Exception as exc:  # noqa: BLE001 - best effort
            result.errors.append(f"activity ingest failed: {exc}")

        if quote_symbols:
            try:
                quotes_payload = rh_bridge.quotes(quote_symbols)
                result.quote_rows = _ingest(
                    conn=conn,
                    kind="quotes",
                    schedule_name="local-live-quotes",
                    parser_name="parse_quote",
                    command=["rh", "quote", *quote_symbols, "--format", "json"],
                    payload=quotes_payload,
                )
            except Exception as exc:  # noqa: BLE001 - best effort
                result.errors.append(f"quotes ingest failed: {exc}")

    return result
