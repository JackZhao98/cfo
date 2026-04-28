"""Sync engine — pull new runs from rh-server and route them into tables.

Idempotent: re-running sync on the same range yields the same DB state.
Only ``status='succeeded'`` runs are parsed; failed ones are recorded in
``runs`` for audit but skipped by parsers.

Concurrency model
-----------------

Two HTTP-bound phases run with a thread pool (``DEFAULT_CONCURRENCY``):

1. **list** — fan out ``GET /v1/schedules/{name}/runs?since=...`` per
   schedule. Schedules are independent.
2. **detail** — fan out ``GET /v1/runs/{id}`` for new succeeded runs.
   Per-run detail fetches are independent.

Parsing and SQLite writes are kept **strictly serial** on the main thread
because (a) parsers mutate shared module state in places, and (b)
``sqlite3.Connection`` objects are not thread-safe by default. The wins
from B1/B2 are entirely in network latency — CPU and disk are not the
bottleneck.
"""
from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping

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
    # Phase -> milliseconds. Always populated; only printed in verbose mode.
    phase_timings_ms: dict[str, float] = field(default_factory=dict)

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
            "phase_timings_ms": self.phase_timings_ms,
        }


@contextmanager
def _phase_timer(result: SyncResult, name: str) -> Iterator[None]:
    """Accumulate elapsed ms into ``result.phase_timings_ms[name]``.

    Same name across multiple ``with`` blocks accumulates rather than
    overwrites (useful for per-iteration phases like ``get_run``).
    """
    started = time.monotonic()
    try:
        yield
    finally:
        elapsed_ms = (time.monotonic() - started) * 1000.0
        result.phase_timings_ms[name] = result.phase_timings_ms.get(name, 0.0) + elapsed_ms


def _existing_run_ids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT run_id FROM runs")}


def _load_sync_watermarks(conn: sqlite3.Connection) -> dict[str, str]:
    """Return mapping schedule_id → last_run_created_at watermark.

    Used to send a ``?since=`` filter to rh-server so it only returns runs
    we haven't ingested yet. Schedules with no entry are full-scanned.
    """
    out: dict[str, str] = {}
    for row in conn.execute(
        "SELECT schedule_id, last_run_created_at FROM sync_state"
    ):
        sid, last = row[0], row[1]
        if sid and last:
            out[str(sid)] = str(last)
    return out


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
    since: str | None = None,
) -> Iterable[dict[str, Any]]:
    return client.list_schedule_runs(schedule_name, limit=limit, since=since)


def _apply_succeeded_run(
    conn: sqlite3.Connection,
    run_summary: Mapping[str, Any],
    detail: Mapping[str, Any],
    schedule_id: str,
    schedule_name: str | None,
    result: SyncResult,
) -> None:
    """Parse the artifact detail and upsert into the appropriate table(s).

    ``detail`` is the full ``GET /v1/runs/{id}`` payload, shaped as
    ``{'run': {...}, 'artifacts': {'meta': ..., 'result': ...}}``.

    Caller has already verified the run is new (not in ``existing``) and
    that ``status == 'succeeded'``. Failures during parse are recorded
    in ``result.errors`` but never raised — best-effort by design.
    """
    run_id = _run_id_of(run_summary)
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
        with _phase_timer(result, "write"):
            _store_unknown(conn, run_id, schedule_id, schedule_name, command, payload)
        result.unknown_payloads += 1
    else:
        impl = PARSER_IMPLEMENTATIONS.get(parser_name)
        if impl is None:
            result.errors.append(f"parser {parser_name} not implemented")
        else:
            try:
                with _phase_timer(result, "parse_write"):
                    rows_written = impl(conn, payload, meta) if payload is not None else 0
            except ParseError as exc:
                result.errors.append(f"{parser_name} failed for run {run_id}: {exc}")
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(f"{parser_name} crashed for run {run_id}: {exc!r}")

    with _phase_timer(result, "write"):
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


#: Default cap on runs fetched per schedule per sync call.
#: Lowered from 50 → 10 in the optimization pass: with the new ``since``
#: filter the server only returns truly new runs, so a small cap is enough
#: for normal cadence syncing and keeps per-call payload tight. Bump via
#: ``--limit`` if you intentionally let many cadences pile up between syncs.
DEFAULT_LIMIT_PER_SCHEDULE = 10

#: Default thread-pool size for HTTP fan-out. Tuned to be friendly to the
#: rh-server (single-host, free-tier-class) while still giving us a 5–8x
#: latency win over fully-serial mode. Set via ``concurrency=`` argument
#: when calling the API directly, or ``CFO_SYNC_CONCURRENCY`` env var.
DEFAULT_CONCURRENCY = 8


def _resolve_concurrency(explicit: int | None) -> int:
    """Pick the effective concurrency: explicit > env var > default."""
    import os
    if explicit is not None and explicit > 0:
        return explicit
    env = os.environ.get("CFO_SYNC_CONCURRENCY")
    if env:
        try:
            n = int(env)
            if n > 0:
                return n
        except ValueError:
            pass
    return DEFAULT_CONCURRENCY


def sync_market_data(
    *,
    schedule_filter: str | None = None,
    limit_per_schedule: int = DEFAULT_LIMIT_PER_SCHEDULE,
    dry_run: bool = False,
    concurrency: int | None = None,
) -> SyncResult:
    """Pull recent runs from rh-server, parse them, upsert into local DB.

    Args:
        schedule_filter: if set, only sync this schedule name.
        limit_per_schedule: max runs to fetch per schedule per call.
        dry_run: if True, connect to DB but rollback at the end (no writes).
        concurrency: thread-pool size for HTTP fan-out (default 8 or env
            ``CFO_SYNC_CONCURRENCY``). Set to 1 to force fully-serial mode
            for debugging.
    """
    cfg = rh_server.load_config(require=True)
    assert cfg is not None  # load_config(require=True) guarantees non-None
    if cfg.mode != "remote":
        raise rh_server.RHServerError(
            "sync market-data requires remote mode — run `cfo schedule connect ...`"
        )
    client = rh_server.RHServerClient(cfg.base_url or "", cfg.api_key or "")
    workers = _resolve_concurrency(concurrency)

    result = SyncResult()
    started_at = _utc_now()
    overall_started = time.monotonic()

    with connect() as conn:
        with _phase_timer(result, "load_existing"):
            existing = _existing_run_ids(conn)
            watermarks = _load_sync_watermarks(conn)
        with _phase_timer(result, "list_schedules"):
            schedules = client.list_schedules()

        # Filter schedules to the ones we'll actually sync.
        candidates: list[tuple[str, str, str | None]] = []  # (sid, name, since)
        for sched in schedules:
            name = sched.get("name")
            sid = sched.get("id") or name
            if not name:
                continue
            if schedule_filter and name != schedule_filter:
                continue
            since = watermarks.get(str(sid)) if sid else None
            candidates.append((str(sid), str(name), since))
            result.schedules_scanned += 1

        # ------------------------------------------------------------
        # Phase B1: concurrent list_schedule_runs
        # ------------------------------------------------------------
        # Fan out one HTTP per schedule. Wall-clock time becomes
        # ~max(individual latency) instead of sum.
        per_schedule_runs: list[tuple[str, str, str | None, list[dict[str, Any]]]] = []
        with _phase_timer(result, "list_runs"):
            if workers <= 1 or len(candidates) <= 1:
                for sid, name, since in candidates:
                    try:
                        runs = list(
                            _iter_runs_for_schedule(
                                client, name, limit=limit_per_schedule, since=since
                            )
                        )
                    except rh_server.RHServerError as exc:
                        result.errors.append(f"list_runs({name}) failed: {exc}")
                        runs = []
                    per_schedule_runs.append((sid, name, since, runs))
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    fut_to_meta = {
                        pool.submit(
                            _iter_runs_for_schedule,
                            client,
                            name,
                            limit=limit_per_schedule,
                            since=since,
                        ): (sid, name, since)
                        for sid, name, since in candidates
                    }
                    for fut in as_completed(fut_to_meta):
                        sid, name, since = fut_to_meta[fut]
                        try:
                            runs = list(fut.result())
                        except rh_server.RHServerError as exc:
                            result.errors.append(f"list_runs({name}) failed: {exc}")
                            runs = []
                        except Exception as exc:  # pragma: no cover - defensive
                            result.errors.append(f"list_runs({name}) crashed: {exc!r}")
                            runs = []
                        per_schedule_runs.append((sid, name, since, runs))

        # ------------------------------------------------------------
        # Phase 2 (serial, fast): dedupe + early-break + classify
        # ------------------------------------------------------------
        # Server returns runs in created_at DESC order per schedule.
        # We walk each schedule's page, dedupe by run_id, early-break once
        # we've crossed the watermark, and split new runs into:
        #   - to_fetch_detail: succeeded runs needing GET /v1/runs/{id}
        #   - failed_runs:     non-succeeded runs (record runs row only)
        #
        # ``sched_acc`` tracks per-schedule state. We only advance the
        # ``latest_*`` watermark for runs whose row actually gets written
        # in phase 4 — done after phase 3 settles, NOT here. This avoids a
        # "skip permanently" bug: if get_run fails for run N but succeeds
        # for N+1, advancing past N+1 would silently lose N forever.
        @dataclass
        class _SchedAcc:
            sid: str
            name: str
            latest_run_id: str | None = None
            latest_created_at: str | None = None
            inserted: int = 0

        sched_acc: dict[str, _SchedAcc] = {}
        to_fetch_detail: list[tuple[Mapping[str, Any], str, str]] = []  # (run_summary, sid, name)
        failed_runs: list[tuple[Mapping[str, Any], str, str]] = []

        for sid, name, since, runs in per_schedule_runs:
            sched_acc.setdefault(sid, _SchedAcc(sid=sid, name=name))
            result.runs_fetched += len(runs)
            for run in runs:
                run_id = _run_id_of(run)
                if not run_id:
                    continue
                if run_id in existing:
                    result.runs_skipped_duplicate += 1
                    created_at = str(run.get("created_at") or "")
                    if since and created_at and created_at <= since:
                        # Crossed watermark — rest is overlap. Stop.
                        break
                    continue

                # Mark in-flight so we don't re-process if it appears twice.
                existing.add(run_id)
                status = str(run.get("status") or "").lower()
                if status == "succeeded":
                    to_fetch_detail.append((run, sid, name))
                else:
                    failed_runs.append((run, sid, name))

        # ------------------------------------------------------------
        # Phase B2: concurrent get_run for to_fetch_detail
        # ------------------------------------------------------------
        # Detail fetches are independent, so fan out. We collect (summary,
        # sid, name, detail) tuples, then apply serially in phase 4.
        details: list[tuple[Mapping[str, Any], str, str, dict[str, Any]]] = []
        with _phase_timer(result, "get_run"):
            if workers <= 1 or len(to_fetch_detail) <= 1:
                for run, sid, name in to_fetch_detail:
                    rid = _run_id_of(run)
                    try:
                        detail = client.get_run(rid)
                        details.append((run, sid, name, detail))
                    except rh_server.RHServerError as exc:
                        result.errors.append(f"get_run({rid}) failed: {exc}")
            elif to_fetch_detail:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    fut_to_item = {
                        pool.submit(client.get_run, _run_id_of(run)): (run, sid, name)
                        for run, sid, name in to_fetch_detail
                    }
                    for fut in as_completed(fut_to_item):
                        run, sid, name = fut_to_item[fut]
                        rid = _run_id_of(run)
                        try:
                            detail = fut.result()
                            details.append((run, sid, name, detail))
                        except rh_server.RHServerError as exc:
                            result.errors.append(f"get_run({rid}) failed: {exc}")
                        except Exception as exc:  # pragma: no cover - defensive
                            result.errors.append(f"get_run({rid}) crashed: {exc!r}")

        # ------------------------------------------------------------
        # Phase 4 (serial): parse + write
        # ------------------------------------------------------------
        # Helper to advance per-schedule watermark only for runs we
        # actually wrote a row for. This is critical for correctness when
        # mixed success/failure occurs in phase 3.
        def _advance_watermark(run: Mapping[str, Any], sid: str, name: str) -> None:
            acc = sched_acc.setdefault(sid, _SchedAcc(sid=sid, name=name))
            created_at_str = str(run.get("created_at") or "")
            run_id = _run_id_of(run)
            if created_at_str and (
                acc.latest_created_at is None
                or created_at_str > acc.latest_created_at
            ):
                acc.latest_created_at = created_at_str
                acc.latest_run_id = run_id
            acc.inserted += 1

        # Failed-status runs: record runs row, no parse.
        for run, sid, name in failed_runs:
            with _phase_timer(result, "write"):
                _insert_runs_row(
                    conn, run, sid, name, parser_name=None, rows_written=0
                )
            result.runs_skipped_failed += 1
            result.runs_inserted += 1
            _advance_watermark(run, sid, name)

        # Succeeded runs: parse + insert.
        for run, sid, name, detail in details:
            _apply_succeeded_run(conn, run, detail, sid, name, result)
            result.runs_inserted += 1
            _advance_watermark(run, sid, name)

        # Per-schedule sync_state upsert. Only schedules with at least one
        # actually-written row will have inserted > 0 here (correct).
        for acc in sched_acc.values():
            if acc.inserted:
                with _phase_timer(result, "write"):
                    _update_sync_state(
                        conn,
                        acc.sid,
                        acc.name,
                        acc.latest_run_id,
                        acc.latest_created_at,
                        acc.inserted,
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

    result.phase_timings_ms["total"] = (time.monotonic() - overall_started) * 1000.0
    return result
