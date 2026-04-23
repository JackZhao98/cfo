"""Sync engine — pull new runs from rh-server and route them into tables.

Idempotent: re-running sync on the same range yields the same DB state.
Only ``status='succeeded'`` runs are parsed; failed ones are recorded in
``runs`` for audit but skipped by parsers.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from cfo.core import rh_server
from cfo.market_db.connection import connect
from cfo.market_db.dispatch import dispatch_parser
from cfo.market_db.parsers import PARSER_IMPLEMENTATIONS, ParseError


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SyncResult:
    schedules_scanned: int = 0
    runs_fetched: int = 0
    runs_inserted: int = 0
    runs_skipped_duplicate: int = 0
    runs_skipped_failed: int = 0
    rows_written: int = 0
    unknown_payloads: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schedules_scanned": self.schedules_scanned,
            "runs_fetched": self.runs_fetched,
            "runs_inserted": self.runs_inserted,
            "runs_skipped_duplicate": self.runs_skipped_duplicate,
            "runs_skipped_failed": self.runs_skipped_failed,
            "rows_written": self.rows_written,
            "unknown_payloads": self.unknown_payloads,
            "errors": self.errors,
        }


def _existing_run_ids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT run_id FROM runs")}


def _update_sync_state(
    conn: sqlite3.Connection,
    schedule_id: str,
    schedule_name: str | None,
    last_run_id: str | None,
    last_run_created_at: str | None,
    inserted_count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO sync_state(
            schedule_id, schedule_name, last_run_id, last_run_created_at,
            last_sync_at, runs_processed_total
        ) VALUES (?,?,?,?,?,?)
        ON CONFLICT(schedule_id) DO UPDATE SET
            schedule_name=excluded.schedule_name,
            last_run_id=COALESCE(excluded.last_run_id, sync_state.last_run_id),
            last_run_created_at=COALESCE(excluded.last_run_created_at, sync_state.last_run_created_at),
            last_sync_at=excluded.last_sync_at,
            runs_processed_total=sync_state.runs_processed_total + ?
        """,
        (
            schedule_id,
            schedule_name,
            last_run_id,
            last_run_created_at,
            _utc_now(),
            inserted_count,
            inserted_count,
        ),
    )


def _run_id_of(summary: Mapping[str, Any]) -> str:
    """Return the run's primary key. rh-server API uses ``id`` in summaries and
    ``artifacts.meta.run_id`` in details. Accept either for robustness."""
    return str(summary.get("id") or summary.get("run_id") or "")


def _command_of_summary(summary: Mapping[str, Any]) -> list[str] | None:
    """Command argv from a run summary lives at ``job_spec.command``."""
    job_spec = summary.get("job_spec")
    if isinstance(job_spec, Mapping):
        cmd = job_spec.get("command")
        if isinstance(cmd, list):
            return cmd
    return None


def _insert_runs_row(
    conn: sqlite3.Connection,
    summary: Mapping[str, Any],
    schedule_id: str,
    schedule_name: str | None,
    parser_name: str | None,
    rows_written: int,
    *,
    extra_meta: Mapping[str, Any] | None = None,
) -> None:
    """Upsert a row into ``runs``. ``summary`` is a run-summary dict as returned
    by ``list_schedule_runs``. ``extra_meta`` is the optional ``artifacts.meta``
    from the detail call when available."""
    command = _command_of_summary(summary)
    if not command and extra_meta:
        cand = extra_meta.get("command")
        if isinstance(cand, list):
            command = cand
    exit_code = None
    if extra_meta:
        exit_code = extra_meta.get("exit_code")
    # Some summaries include ``result.exit_code`` too.
    if exit_code is None:
        result_block = summary.get("result")
        if isinstance(result_block, Mapping):
            exit_code = result_block.get("exit_code")

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
            _run_id_of(summary),
            schedule_id,
            schedule_name,
            str(summary.get("status") or "unknown"),
            exit_code,
            str(summary.get("created_at") or ""),
            str(summary.get("started_at") or ""),
            str(summary.get("finished_at") or ""),
            json.dumps(command) if command else None,
            parser_name,
            rows_written,
            _utc_now(),
        ),
    )


def _store_unknown(
    conn: sqlite3.Connection,
    run_id: str,
    schedule_id: str,
    schedule_name: str | None,
    command: Any,
    payload: Any,
) -> None:
    conn.execute(
        """
        INSERT INTO unknown_payloads(
            run_id, schedule_id, schedule_name, command_json,
            payload_json, ingested_at, notes
        ) VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(run_id) DO NOTHING
        """,
        (
            run_id,
            schedule_id,
            schedule_name,
            json.dumps(command) if command else None,
            json.dumps(payload)[:1_000_000],  # safety cap at ~1 MB
            _utc_now(),
            "no parser registered for this command",
        ),
    )


def _iter_runs_for_schedule(
    client: rh_server.RHServerClient,
    schedule_name: str,
    *,
    limit: int,
) -> Iterable[dict[str, Any]]:
    return client.list_schedule_runs(schedule_name, limit=limit)


def _process_run(
    conn: sqlite3.Connection,
    client: rh_server.RHServerClient,
    run_summary: Mapping[str, Any],
    schedule_id: str,
    schedule_name: str | None,
    result: SyncResult,
) -> str | None:
    """Fetch full run detail, dispatch parser, insert row. Returns run_id."""
    run_id = _run_id_of(run_summary)
    if not run_id:
        result.errors.append(f"skip: run missing id: {dict(run_summary)!r}")
        return None

    status = str(run_summary.get("status") or "").lower()
    if status != "succeeded":
        # record the run for audit but don't parse
        _insert_runs_row(
            conn, run_summary, schedule_id, schedule_name, parser_name=None, rows_written=0
        )
        result.runs_skipped_failed += 1
        return run_id

    # Fetch full artifact. API returns {'run': {...}, 'artifacts': {'meta': ..., 'result': ..., ...}}.
    try:
        detail = client.get_run(run_id)
    except rh_server.RHServerError as exc:
        result.errors.append(f"get_run({run_id}) failed: {exc}")
        return run_id

    artifacts = detail.get("artifacts") or {}
    meta = artifacts.get("meta") if isinstance(artifacts, Mapping) else None
    if not isinstance(meta, Mapping):
        meta = {}
    result_block = artifacts.get("result") if isinstance(artifacts, Mapping) else None
    payload = None
    if isinstance(result_block, Mapping):
        payload = result_block.get("payload")

    # Command is authoritative from meta; fall back to summary job_spec.
    command = meta.get("command")
    if not isinstance(command, list):
        command = _command_of_summary(run_summary) or []

    # For parsers, meta must include the run_id (parsers rely on it).
    if "run_id" not in meta:
        meta = {**meta, "run_id": run_id, "command": command}

    parser_name = dispatch_parser(command)
    rows_written = 0

    if parser_name is None:
        _store_unknown(conn, run_id, schedule_id, schedule_name, command, payload)
        result.unknown_payloads += 1
    else:
        impl = PARSER_IMPLEMENTATIONS.get(parser_name)
        if impl is None:
            result.errors.append(f"parser {parser_name} not implemented")
        else:
            try:
                rows_written = impl(conn, payload, meta) if payload is not None else 0
            except ParseError as exc:
                result.errors.append(f"{parser_name} failed for run {run_id}: {exc}")
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(f"{parser_name} crashed for run {run_id}: {exc!r}")

    _insert_runs_row(
        conn,
        run_summary,
        schedule_id,
        schedule_name,
        parser_name,
        rows_written,
        extra_meta=meta,
    )
    result.rows_written += rows_written
    return run_id


def sync_market_data(
    *,
    schedule_filter: str | None = None,
    limit_per_schedule: int = 50,
    dry_run: bool = False,
) -> SyncResult:
    """Pull recent runs from rh-server, parse them, upsert into local DB.

    Args:
        schedule_filter: if set, only sync this schedule name.
        limit_per_schedule: max runs to fetch per schedule per call.
        dry_run: if True, connect to DB but rollback at the end (no writes).
    """
    cfg = rh_server.load_config(require=True)
    assert cfg is not None  # load_config(require=True) guarantees non-None
    if cfg.mode != "remote":
        raise rh_server.RHServerError(
            "sync market-data requires remote mode — run `cfo schedule connect ...`"
        )
    client = rh_server.RHServerClient(cfg.base_url or "", cfg.api_key or "")

    result = SyncResult()
    started_at = _utc_now()

    with connect() as conn:
        existing = _existing_run_ids(conn)
        schedules = client.list_schedules()
        for sched in schedules:
            name = sched.get("name")
            sid = sched.get("id") or name
            if not name:
                continue
            if schedule_filter and name != schedule_filter:
                continue
            result.schedules_scanned += 1

            runs = list(_iter_runs_for_schedule(client, name, limit=limit_per_schedule))
            result.runs_fetched += len(runs)

            latest_run_id = None
            latest_created_at = None
            inserted_for_this_schedule = 0

            for run in runs:
                run_id = _run_id_of(run)
                if not run_id:
                    continue
                if run_id in existing:
                    result.runs_skipped_duplicate += 1
                    continue
                processed_id = _process_run(conn, client, run, sid, name, result)
                if processed_id:
                    existing.add(processed_id)
                    inserted_for_this_schedule += 1
                    result.runs_inserted += 1
                    created_at = run.get("created_at")
                    if created_at and (latest_created_at is None or str(created_at) > latest_created_at):
                        latest_created_at = str(created_at)
                        latest_run_id = run_id

            if inserted_for_this_schedule:
                _update_sync_state(
                    conn,
                    sid,
                    name,
                    latest_run_id,
                    latest_created_at,
                    inserted_for_this_schedule,
                )

        # Write one summary ingest_log row
        conn.execute(
            """
            INSERT INTO ingest_log(
                sync_started_at, sync_finished_at, schedule_id, schedule_name,
                runs_fetched, runs_inserted, runs_skipped, rows_written,
                errors_json
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                started_at,
                _utc_now(),
                schedule_filter or "ALL",
                schedule_filter,
                result.runs_fetched,
                result.runs_inserted,
                result.runs_skipped_duplicate + result.runs_skipped_failed,
                result.rows_written,
                json.dumps(result.errors) if result.errors else None,
            ),
        )

        if dry_run:
            conn.rollback()

    return result
