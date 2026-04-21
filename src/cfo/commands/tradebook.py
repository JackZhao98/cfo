"""cfo tradebook — add / show / reconcile."""
import json
import time
import uuid
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import tradebook as core
from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource
from cfo.util import audit, paths

console = Console()
tradebook_app = typer.Typer(help="Tradebook (real + paper trades).")


@tradebook_app.command("add")
def add(
    paper: bool = typer.Option(False, "--paper", help="Mark as paper trade."),
    account: str = typer.Option(..., "--account", "-a"),
    symbol: str = typer.Option(..., "--symbol", "-s"),
    side: TradeSide = typer.Option(..., "--side"),
    qty: float = typer.Option(..., "--qty"),
    price: float | None = typer.Option(None, "--price"),
    total: float | None = typer.Option(None, "--total"),
    strategy: str | None = typer.Option(None, "--strategy"),
    strike: float | None = typer.Option(None, "--strike"),
    exp: str | None = typer.Option(None, "--exp"),
    premium: float | None = typer.Option(None, "--premium"),
    notes: str = typer.Option("", "--notes"),
):
    """Append one trade to master.jsonl. Use --paper for paper trades."""
    start = time.monotonic()
    t = Trade(
        id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc),
        mode=TradeMode.paper if paper else TradeMode.real,
        account_id=account,
        source=TradeSource.cfo,
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        total=total,
        strategy=strategy,
        strike=strike,
        exp=exp,
        premium=premium,
        notes=notes,
    )
    core.append(t)
    console.print(f"[green]ok[/green] {t.mode.value} {t.side.value} {t.qty} {t.symbol} → appended")
    audit.record(cmd=["cfo", "tradebook", "add", symbol, side.value], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@tradebook_app.command("show")
def show(
    mode: TradeMode | None = typer.Option(None, "--mode"),
    strategy: str | None = typer.Option(None, "--strategy"),
    symbol: str | None = typer.Option(None, "--symbol"),
    month: str | None = typer.Option(None, "--month", help="YYYY-MM"),
    account: str | None = typer.Option(None, "--account"),
    limit: int = typer.Option(50, "--limit"),
):
    """Show trades with optional filters."""
    start = time.monotonic()
    trades = core.filter_trades(mode=mode, strategy=strategy, symbol=symbol, month=month, account_id=account)
    trades = trades[-limit:]
    if not trades:
        console.print("[yellow]no trades match[/yellow]")
        audit.record(cmd=["cfo", "tradebook", "show"], result="ok",
                     duration_ms=int((time.monotonic() - start) * 1000))
        return
    t = Table(title=f"Tradebook ({len(trades)} trades)")
    for col in ("TS", "Mode", "Account", "Symbol", "Side", "Qty", "Price", "Total", "Strategy"):
        t.add_column(col)
    for tr in trades:
        t.add_row(
            tr.ts.isoformat(timespec="minutes"),
            tr.mode.value,
            tr.account_id,
            tr.symbol,
            tr.side.value,
            f"{tr.qty:g}",
            f"{tr.price:.2f}" if tr.price is not None else "-",
            f"{tr.total:.2f}" if tr.total is not None else "-",
            tr.strategy or "-",
        )
    console.print(t)
    audit.record(cmd=["cfo", "tradebook", "show"], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@tradebook_app.command("reconcile")
def reconcile():
    """Diff rh raw trades.jsonl vs cfo master where source=rh, by rh_order_id."""
    start = time.monotonic()
    rh_log = paths.rh_raw_trades_jsonl()
    if not rh_log.exists():
        console.print("[yellow]no rh log at " + str(rh_log) + "[/yellow]")
        audit.record(cmd=["cfo", "tradebook", "reconcile"], result="ok",
                     duration_ms=int((time.monotonic() - start) * 1000))
        return
    rh_ids: set[str] = set()
    for line in rh_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        oid = rec.get("rh_order_id") or rec.get("id")
        if oid:
            rh_ids.add(oid)
    cfo_ids = {t.rh_order_id for t in core.filter_trades(mode=TradeMode.real) if t.rh_order_id}
    missing_in_cfo = rh_ids - cfo_ids
    extra_in_cfo = cfo_ids - rh_ids
    if not missing_in_cfo and not extra_in_cfo:
        console.print("[green]reconciled ok[/green] — all rh orders match cfo master")
        audit.record(cmd=["cfo", "tradebook", "reconcile"], result="ok",
                     duration_ms=int((time.monotonic() - start) * 1000))
        return
    if missing_in_cfo:
        console.print(f"[red]{len(missing_in_cfo)} rh orders not in cfo master:[/red]")
        for oid in missing_in_cfo:
            console.print(f"  - {oid}")
    if extra_in_cfo:
        console.print(f"[red]{len(extra_in_cfo)} cfo trades have no matching rh order:[/red]")
        for oid in extra_in_cfo:
            console.print(f"  - {oid}")
    audit.record(cmd=["cfo", "tradebook", "reconcile"], result="error",
                 duration_ms=int((time.monotonic() - start) * 1000))
    raise typer.Exit(code=1)
