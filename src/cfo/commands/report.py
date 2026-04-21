"""cfo report — weekly / monthly / audit."""
import time
from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import audit_query
from cfo.core import history as core_history
from cfo.core import report as core_report
from cfo.util import audit, paths, timerange

console = Console()
report_app = typer.Typer(help="Auto-generated weekly / monthly markdown reports.")


@report_app.command("weekly")
def weekly() -> None:
    """Generate this week's markdown report to data/reports/."""
    started = time.monotonic()
    today = date.today()
    md = core_report.weekly(today=today)
    week_id = timerange.iso_week_id(today)
    out = paths.reports_dir() / f"{week_id}-weekly.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    console.print(f"[green]ok[/green] weekly report → {out}")
    audit.record(
        cmd=["cfo", "report", "weekly"],
        result="ok",
        duration_ms=int((time.monotonic() - started) * 1000),
    )


@report_app.command("monthly")
def monthly() -> None:
    """Generate this month's report + freeze current portfolio to history/."""
    started = time.monotonic()
    today = date.today()
    month_id = timerange.month_id(today)
    # Snapshot current state first so the report can include delta
    core_history.snapshot_current(label=month_id)
    md = core_report.monthly(today=today)
    out = paths.reports_dir() / f"{month_id}-monthly.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    console.print(f"[green]ok[/green] monthly report → {out}")
    console.print(
        f"[green]ok[/green] portfolio snapshot → "
        f"{paths.portfolio_history_dir() / f'{month_id}.json'}"
    )
    audit.record(
        cmd=["cfo", "report", "monthly"],
        result="ok",
        duration_ms=int((time.monotonic() - started) * 1000),
    )


@report_app.command("audit")
def audit_summary_cmd(
    since: str = typer.Option(..., "--since", help="YYYY-MM-DD"),
    until: str = typer.Option(..., "--until", help="YYYY-MM-DD"),
) -> None:
    """Summarize audit log for a date range."""
    started = time.monotonic()
    try:
        start = date.fromisoformat(since)
        end = date.fromisoformat(until)
    except ValueError as e:
        console.print(f"[red]invalid date: {e}[/red]")
        raise typer.Exit(1)
    s = audit_query.summarize(start, end)
    if s["total"] == 0:
        console.print(
            f"[yellow]no audit records between {since} and {until}[/yellow]"
        )
        audit.record(
            cmd=["cfo", "report", "audit"],
            result="ok",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return
    console.print(
        f"[bold]{s['total']}[/bold] invocations between {since} and {until}: "
        f"[green]{s['ok']} ok[/green], [red]{s['error']} error[/red]"
    )
    if s["by_command"]:
        t = Table(title="By command")
        t.add_column("Command")
        t.add_column("Count", justify="right")
        for cmd, n in sorted(s["by_command"].items(), key=lambda x: -x[1]):
            t.add_row(cmd, str(n))
        console.print(t)
    audit.record(
        cmd=["cfo", "report", "audit"],
        result="ok",
        duration_ms=int((time.monotonic() - started) * 1000),
    )
