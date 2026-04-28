"""``cfo db`` — init, status, stats, reset, vacuum for the market database."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from cfo.market_db import connection
from cfo.market_db import sync as sync_module
from cfo.market_db.sync import sync_market_data


console = Console()
db_app = typer.Typer(help="Local SQLite market database for backtesting.")


@db_app.command("init")
def init_cmd() -> None:
    """Create the market DB file (idempotent)."""
    path = connection.init_db()
    typer.echo(f"ok market DB ready at {path}")


@db_app.command("status")
def status_cmd() -> None:
    """Show per-schedule sync watermarks + table row counts."""
    try:
        with connection.connect(read_only=True) as conn:
            table = Table(title="Sync state (per schedule)")
            table.add_column("Schedule")
            table.add_column("Last run (UTC)")
            table.add_column("Total ingested", justify="right")
            table.add_column("Last synced (UTC)")

            rows = conn.execute(
                """
                SELECT schedule_name, last_run_created_at,
                       runs_processed_total, last_sync_at
                  FROM sync_state
                 ORDER BY schedule_name
                """
            ).fetchall()
            if not rows:
                typer.echo("no sync state yet — run `cfo sync market-data`")
            else:
                for r in rows:
                    table.add_row(
                        r["schedule_name"] or "?",
                        r["last_run_created_at"] or "-",
                        str(r["runs_processed_total"] or 0),
                        r["last_sync_at"] or "-",
                    )
                console.print(table)

            _print_table_counts(conn)

            unk = conn.execute("SELECT COUNT(*) FROM unknown_payloads").fetchone()[0]
            if unk:
                console.print(
                    f"\n[yellow]⚠  {unk} unknown payloads — add parsers to handle them[/yellow]"
                )
    except connection.MarketDBError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def _print_table_counts(conn) -> None:
    data_tables = [
        "runs",
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
        "unknown_payloads",
    ]
    t = Table(title="Table row counts")
    t.add_column("Table")
    t.add_column("Rows", justify="right")
    t.add_column("Earliest", justify="right")
    t.add_column("Latest", justify="right")
    for name in data_tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        except Exception:
            continue
        # Try to find earliest/latest ts or created_at
        earliest = latest = "-"
        for col in ("ts", "created_at", "published_at", "ingested_at"):
            try:
                row = conn.execute(
                    f"SELECT MIN({col}), MAX({col}) FROM {name}"
                ).fetchone()
                if row and row[0]:
                    earliest = row[0]
                    latest = row[1]
                    break
            except Exception:
                continue
        t.add_row(name, str(count), earliest, latest)
    console.print(t)


@db_app.command("reset")
def reset_cmd(
    schedule: str = typer.Option(..., "--schedule", help="Schedule name to reset"),
) -> None:
    """Wipe the sync watermark for one schedule (next sync will re-pull it)."""
    with connection.connect() as conn:
        cur = conn.execute(
            "DELETE FROM sync_state WHERE schedule_name = ?", (schedule,)
        )
        if cur.rowcount == 0:
            typer.echo(f"no sync state found for {schedule}")
        else:
            typer.echo(f"ok reset watermark for {schedule}")


@db_app.command("vacuum")
def vacuum_cmd() -> None:
    """Compact the SQLite file (reclaims space after heavy updates)."""
    with connection.connect() as conn:
        conn.execute("VACUUM")
    typer.echo("ok vacuumed market.db")


@db_app.command("sync")
def sync_cmd(
    schedule: str | None = typer.Option(
        None, "--schedule", help="Only sync this schedule (default: all)"
    ),
    limit: int = typer.Option(
        sync_module.DEFAULT_LIMIT_PER_SCHEDULE,
        "--limit",
        help="Max runs to fetch per schedule per call (default: 10).",
    ),
    concurrency: int = typer.Option(
        0,
        "--concurrency",
        help=(
            "Thread-pool size for HTTP fan-out (0 = use default 8 or "
            "$CFO_SYNC_CONCURRENCY env var). Set to 1 to force fully-serial."
        ),
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Don't commit; show what would happen"
    ),
    verbose_timing: bool = typer.Option(
        False, "--verbose-timing", help="Print per-phase timing breakdown."
    ),
) -> None:
    """Pull new runs from rh-server, parse, and upsert into local DB.

    Alias for ``cfo sync market-data`` (same implementation). Placed under
    ``cfo db sync`` so folks who find the DB namespace first don't have to
    remember it lives elsewhere.
    """
    result = sync_market_data(
        schedule_filter=schedule,
        limit_per_schedule=limit,
        dry_run=dry_run,
        concurrency=concurrency or None,
    )
    _print_sync_result(result, dry_run=dry_run, verbose_timing=verbose_timing)


def _print_sync_result(result, *, dry_run: bool, verbose_timing: bool = False) -> None:
    t = Table(title=("Sync result (DRY RUN)" if dry_run else "Sync result"))
    t.add_column("Metric")
    t.add_column("Value", justify="right")
    skip_keys = {"errors", "phase_timings_ms"}
    for k, v in result.as_dict().items():
        if k in skip_keys:
            continue
        t.add_row(k, str(v))
    console.print(t)
    if verbose_timing:
        timings = getattr(result, "phase_timings_ms", None) or {}
        if timings:
            tt = Table(title="Phase timings (ms)")
            tt.add_column("Phase")
            tt.add_column("ms", justify="right")
            order = ["load_existing", "list_schedules", "list_runs", "get_run", "parse_write", "write", "total"]
            for key in order:
                val = timings.get(key)
                if val is None:
                    continue
                tt.add_row(key, f"{val:.0f}")
            console.print(tt)
    if result.errors:
        console.print("\n[yellow]Errors:[/yellow]")
        for err in result.errors[:10]:
            console.print(f"  • {err}")
        if len(result.errors) > 10:
            console.print(f"  … and {len(result.errors) - 10} more")
