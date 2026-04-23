"""cfo market — index dashboard ("pulse").

The ``pulse`` subcommand renders a one-glance sentiment dashboard from the
rh index values/fundamentals endpoints, with 52-week percentile and
day-over-day change pre-computed so the user (or Claude) doesn't have to
eyeball raw numbers.
"""
import time
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import rh_bridge
from cfo.core import wheel_risk as core_wheel_risk
from cfo.util import audit
from cfo.util.render import OutputFormat, render_json, render_plain

console = Console()
market_app = typer.Typer(help="Market-wide sentiment dashboard.")


DEFAULT_PULSE_SYMBOLS = ("SPX", "NDX", "RUT", "DJX", "VIX", "MGTN", "CBTX")


def _pct_of_range(value: float, lo: Optional[float], hi: Optional[float]) -> Optional[float]:
    """Return where `value` sits in [lo, hi] as a percent (0-100)."""
    if lo is None or hi is None or hi <= lo:
        return None
    return (value - lo) / (hi - lo) * 100


def _pct_change(value: float, prev: Optional[float]) -> Optional[float]:
    if prev is None or prev == 0:
        return None
    return (value / prev - 1) * 100


def _position_label(pct: Optional[float]) -> str:
    """Colour hint for % of 52w range."""
    if pct is None:
        return ""
    if pct >= 95:
        return "[bold red]near-top[/bold red]"
    if pct >= 80:
        return "[red]high[/red]"
    if pct <= 20:
        return "[green]low[/green]"
    if pct <= 40:
        return "[green]lower-mid[/green]"
    return "mid"


@market_app.command("pulse")
def pulse(
    symbols: Optional[list[str]] = typer.Argument(
        None,
        help="Symbols to include (default: SPX NDX RUT DJX VIX MGTN CBTX).",
    ),
    all_registered: bool = typer.Option(
        False, "--all", help="Use every symbol registered in `rh index --list`."
    ),
):
    """One-glance index dashboard (value, day Δ, 52w percentile, PE)."""
    start = time.monotonic()

    if all_registered:
        syms = rh_bridge.index_list()
    elif symbols:
        syms = [s.upper() for s in symbols]
    else:
        syms = list(DEFAULT_PULSE_SYMBOLS)

    if not syms:
        console.print("[yellow]no indexes registered — run `rh index --register SYM=<uuid>` first.[/yellow]")
        raise typer.Exit(code=1)

    try:
        rows = rh_bridge.index_values(syms)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "market", "pulse", *syms],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(code=1)

    table = Table(title=f"Market Pulse ({', '.join(r['symbol'] for r in rows)})")
    table.add_column("SYM")
    table.add_column("Value", justify="right")
    table.add_column("Prev", justify="right")
    table.add_column("Δ%", justify="right")
    table.add_column("52w Low", justify="right")
    table.add_column("52w High", justify="right")
    table.add_column("% of 52w", justify="right")
    table.add_column("PE", justify="right")
    table.add_column("Position")

    for r in rows:
        v = r.get("value")
        prev = r.get("previous_close")
        lo52 = r.get("low_52_weeks")
        hi52 = r.get("high_52_weeks")
        pe = r.get("pe_ratio")

        chg = _pct_change(v, prev)
        pos = _pct_of_range(v, lo52, hi52)

        chg_str = "—" if chg is None else f"{chg:+.2f}%"
        chg_style = ""
        if chg is not None:
            chg_style = "[green]" if chg > 0 else ("[red]" if chg < 0 else "")
            if chg_style:
                chg_str = f"{chg_style}{chg_str}[/{chg_style.strip('[]')}]"

        table.add_row(
            r["symbol"],
            f"{v:,.2f}" if v is not None else "—",
            f"{prev:,.2f}" if prev is not None else "—",
            chg_str,
            f"{lo52:,.2f}" if lo52 is not None else "—",
            f"{hi52:,.2f}" if hi52 is not None else "—",
            f"{pos:.1f}%" if pos is not None else "—",
            f"{pe:.1f}" if pe is not None else "—",
            _position_label(pos),
        )

    console.print(table)
    audit.record(
        cmd=["cfo", "market", "pulse", *syms],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@market_app.command("wheel-risk")
def wheel_risk_cmd(
    symbol: str = typer.Argument(..., help="Underlying ticker, e.g. SOFI."),
    exp: Optional[str] = typer.Option(None, "--exp", help="Explicit expiration YYYY-MM-DD. Defaults to nearest ~35 DTE."),
    min_dte: int = typer.Option(21, "--min-dte", min=1, help="Minimum DTE when auto-picking an expiration."),
    max_dte: int = typer.Option(60, "--max-dte", min=1, help="Maximum DTE when auto-picking an expiration."),
    limit: int = typer.Option(6, "--limit", min=1, max=20, help="How many put strikes to show."),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", help="table | plain | json"),
):
    """Score wheel risk using IV, HV, earnings, headlines, and option-chain data."""
    start = time.monotonic()
    symbol = symbol.upper()
    try:
        report = core_wheel_risk.analyze_symbol(
            symbol,
            expiration=exp,
            min_dte=min_dte,
            max_dte=max_dte,
            limit=limit,
        )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "market", "wheel-risk", symbol],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(code=1)

    payload = report.to_dict()
    if format == OutputFormat.json:
        render_json(console, payload)
    elif format == OutputFormat.plain:
        render_plain(console, payload)
    else:
        summary = Table(title=f"Wheel Risk — {report.symbol}")
        summary.add_column("Metric")
        summary.add_column("Value", justify="right")
        summary.add_row("Spot", f"{report.spot_price:,.2f}")
        summary.add_row("Expiration", f"{report.selected_expiration} ({report.dte} DTE)")
        summary.add_row("Stock Risk", f"{report.stock_risk_score:.1f}/100 ({report.stock_risk_label})")
        summary.add_row("Current IV", f"{report.current_iv:.2%}" if report.current_iv is not None else "—")
        summary.add_row("HV20 / HV60", (
            f"{report.hv20:.2%} / {report.hv60:.2%}"
            if report.hv20 is not None and report.hv60 is not None
            else "—"
        ))
        summary.add_row("IV / HV20", f"{report.iv_hv20_ratio:.2f}x" if report.iv_hv20_ratio is not None else "—")
        summary.add_row("IV Rank 90d", f"{report.iv_rank_90d:.1f}" if report.iv_rank_90d is not None else "—")
        summary.add_row(
            "Next Earnings",
            (
                f"{report.next_earnings_date} ({report.days_to_earnings}d)"
                + (" — before exp" if report.earnings_before_expiration else "")
            )
            if report.next_earnings_date
            else "—"
        )
        summary.add_row(
            "Past Earnings Gap",
            (
                f"avg {report.avg_earnings_gap_pct:.2f}% / max {report.max_earnings_gap_pct:.2f}%"
                if report.avg_earnings_gap_pct is not None and report.max_earnings_gap_pct is not None
                else "—"
            ),
        )
        summary.add_row("News Sentiment", f"{report.news_sentiment:+.2f} ({report.news_heat_72h} / 72h)")
        summary.add_row("VIX", f"{report.vix:.2f}" if report.vix is not None else "—")
        summary.add_row("Model Read", report.summary)
        console.print(summary)

        components = Table(title="Risk Components")
        components.add_column("Component")
        components.add_column("Score", justify="right")
        for key, value in report.components.items():
            components.add_row(key.replace("_", " "), f"{value:.1f}")
        console.print(components)

        candidates = Table(title=f"Top Sell Put Candidates ({len(report.top_candidates)})")
        candidates.add_column("Strike", justify="right")
        candidates.add_column("Premium", justify="right")
        candidates.add_column("BE", justify="right")
        candidates.add_column("Δ", justify="right")
        candidates.add_column("IV", justify="right")
        candidates.add_column("Ann Yield", justify="right")
        candidates.add_column("Buffer", justify="right")
        candidates.add_column("Risk", justify="right")
        candidates.add_column("Fit", justify="right")
        candidates.add_column("Notes")
        for row in report.top_candidates:
            candidates.add_row(
                f"{row.strike:.2f}",
                f"{row.premium:.3f}",
                f"{row.break_even:.2f}",
                f"{row.delta:.3f}" if row.delta is not None else "—",
                f"{row.iv:.1%}" if row.iv is not None else "—",
                f"{row.annualized_yield_pct:.1f}%",
                f"{row.break_even_buffer_pct:.1f}%",
                f"{row.candidate_risk:.1f}",
                f"{row.wheel_fit_score:.1f}",
                ", ".join(row.notes) if row.notes else "",
            )
        console.print(candidates)

    audit.record(
        cmd=["cfo", "market", "wheel-risk", symbol],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@market_app.command("wheel-backtest")
def wheel_backtest_cmd(
    symbol: str = typer.Argument(..., help="Underlying ticker, e.g. SOFI."),
    exp: Optional[str] = typer.Option(None, "--exp", help="Explicit expiration YYYY-MM-DD. Defaults to nearest ~35 DTE."),
    min_dte: int = typer.Option(21, "--min-dte", min=1, help="Minimum DTE when auto-picking an expiration."),
    max_dte: int = typer.Option(60, "--max-dte", min=1, help="Maximum DTE when auto-picking an expiration."),
    candidate_limit: int = typer.Option(3, "--candidate-limit", min=1, max=10, help="How many current candidate puts to replay."),
    lookback_days: int = typer.Option(252, "--lookback-days", min=30, help="How many trading days of history to replay."),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", help="table | plain | json"),
):
    """Approximate path backtest for current wheel candidates using historical closes."""
    start = time.monotonic()
    symbol = symbol.upper()
    try:
        report = core_wheel_risk.backtest_symbol(
            symbol,
            expiration=exp,
            min_dte=min_dte,
            max_dte=max_dte,
            candidate_limit=candidate_limit,
            lookback_days=lookback_days,
        )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "market", "wheel-backtest", symbol],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(code=1)

    payload = report.to_dict()
    if format == OutputFormat.json:
        render_json(console, payload)
    elif format == OutputFormat.plain:
        render_plain(console, payload)
    else:
        summary = Table(title=f"Wheel Path Backtest — {report.symbol}")
        summary.add_column("Metric")
        summary.add_column("Value", justify="right")
        summary.add_row("Current Risk", f"{report.current_stock_risk_score:.1f}/100 ({report.current_stock_risk_label})")
        summary.add_row("Expiration / DTE", f"{report.expiration} / {report.dte}")
        summary.add_row("Replay Samples", str(report.evaluation_count))
        summary.add_row("Lookback", f"{report.lookback_days} days")
        summary.add_row("Method", report.source_summary)
        console.print(summary)

        rows = Table(title=f"Replay Results ({len(report.rows)} candidates)")
        rows.add_column("Strike", justify="right")
        rows.add_column("BE", justify="right")
        rows.add_column("Fit", justify="right")
        rows.add_column("Ann Yield", justify="right")
        rows.add_column("Strike Breach", justify="right")
        rows.add_column("BE Breach", justify="right")
        rows.add_column("Assigned", justify="right")
        rows.add_column("Finish > BE", justify="right")
        rows.add_column("Avg Terminal", justify="right")
        rows.add_column("Worst DD", justify="right")
        for row in report.rows:
            rows.add_row(
                f"{row.strike:.2f}",
                f"{row.break_even:.2f}",
                f"{row.wheel_fit_score:.1f}",
                f"{row.annualized_yield_pct:.1f}%",
                f"{row.strike_breach_rate:.1f}%",
                f"{row.break_even_breach_rate:.1f}%",
                f"{row.assigned_rate:.1f}%",
                f"{row.finish_above_break_even_rate:.1f}%",
                f"{row.avg_terminal_return_pct:.1f}%",
                f"{row.worst_window_drawdown_pct:.1f}%",
            )
        console.print(rows)

    audit.record(
        cmd=["cfo", "market", "wheel-backtest", symbol],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )
