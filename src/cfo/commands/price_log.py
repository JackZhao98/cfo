"""cfo price-log — snap / show daily quote snapshots."""
import time

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import price_log as core
from cfo.util import audit

console = Console()
price_log_app = typer.Typer(help="Daily price snapshots.")


@price_log_app.command("snap")
def snap(
    symbol: list[str] = typer.Option(
        [], "--symbol", "-s",
        help="Symbol to snap; repeat --symbol for multiple",
    ),
    watchlist: bool = typer.Option(
        False, "--watchlist",
        help="Include default watchlist (holdings + price-log/watchlist.txt)",
    ),
):
    """Snap quotes for the given symbols (and/or watchlist) to today's jsonl."""
    start = time.monotonic()
    symbols = list(symbol)
    if watchlist:
        symbols = symbols + core.default_watchlist()
    symbols = sorted(set(symbols))
    if not symbols:
        console.print(
            "[yellow]watchlist empty — pass --symbol or populate "
            "data/price-log/watchlist.txt[/yellow]"
        )
        audit.record(
            cmd=["cfo", "price-log", "snap"],
            result="ok",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        return
    n = core.snap(symbols)
    console.print(
        f"[green]ok[/green] {n} quote(s) snapped for {len(symbols)} symbol(s)"
    )
    audit.record(
        cmd=["cfo", "price-log", "snap"],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@price_log_app.command("show")
def show(
    symbol: str = typer.Argument(...),
    days: int = typer.Option(7, "--days"),
):
    """Show historical snapped quotes for a symbol."""
    history = core.show(symbol, days=days)
    if not history:
        console.print(f"[yellow]no data for {symbol} in last {days} days[/yellow]")
        return
    t = Table(title=f"{symbol} — last {days} days ({len(history)} snaps)")
    for col in ("Snapped", "Last", "Bid", "Ask", "High", "Low", "Volume"):
        t.add_column(col)
    for r in history:
        t.add_row(
            r.get("cfo_snap_ts", "-"),
            f"{r.get('last_price', 0):.2f}" if r.get("last_price") is not None else "-",
            f"{r.get('bid', 0):.2f}" if r.get("bid") is not None else "-",
            f"{r.get('ask', 0):.2f}" if r.get("ask") is not None else "-",
            f"{r.get('high', 0):.2f}" if r.get("high") is not None else "-",
            f"{r.get('low', 0):.2f}" if r.get("low") is not None else "-",
            str(r.get("volume", "-")),
        )
    console.print(t)
