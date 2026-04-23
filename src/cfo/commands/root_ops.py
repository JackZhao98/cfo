"""Top-level ergonomic commands: sync / status."""
import time

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import paper as core_paper
from cfo.core import price_log as core_price_log
from cfo.core import portfolio as core_portfolio
from cfo.core import strategy as core_strategy
from cfo.core import tradebook as core_tradebook
from cfo.schemas.tradebook import TradeMode
from cfo.util import audit
from cfo.commands import portfolio as portfolio_cmd
from cfo.util.render import OutputFormat, format_local_dt, render_json, render_plain

console = Console()


def _latest_tracked_quotes() -> list[dict]:
    symbols = core_price_log.default_watchlist()
    if not symbols:
        return []
    try:
        from cfo.market_db.connection import connect
    except Exception:
        return []

    out: list[dict] = []
    try:
        with connect(read_only=True) as conn:
            for sym in symbols:
                row = conn.execute(
                    """
                    SELECT symbol, ts, current_price, day_change_pct
                      FROM quotes
                     WHERE symbol = ?
                     ORDER BY ts DESC
                     LIMIT 1
                    """,
                    (sym,),
                ).fetchone()
                if not row:
                    continue
                out.append(
                    {
                        "symbol": row["symbol"],
                        "ts": row["ts"],
                        "current_price": row["current_price"],
                        "day_change_pct": row["day_change_pct"],
                    }
                )
    except Exception:
        return []
    return out


def _latest_live_activity(limit: int) -> list[dict]:
    if limit <= 0:
        return []
    try:
        from cfo.market_db.connection import connect
    except Exception:
        return []

    out: list[dict] = []
    try:
        with connect(read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT created_at, account_number, symbol, side, quantity, price, state, order_id
                  FROM activity
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
            for row in rows:
                out.append(
                    {
                        "created_at": row["created_at"],
                        "account_number": row["account_number"],
                        "symbol": row["symbol"],
                        "side": row["side"],
                        "quantity": row["quantity"],
                        "price": row["price"],
                        "state": row["state"],
                        "order_id": row["order_id"],
                    }
                )
    except Exception:
        return []
    return out


def sync_cmd(
    portfolio: bool = typer.Option(True, "--portfolio/--no-portfolio", help="Refresh Robinhood account balances and holdings."),
    import_rh: bool = typer.Option(True, "--import-rh/--no-import-rh", help="Import missing real trades from ~/.config/rh/trades.jsonl."),
    refresh_orders: bool = typer.Option(True, "--refresh-orders/--no-refresh-orders", help="Refresh tracked order states from Robinhood."),
    all_orders: bool = typer.Option(False, "--all-orders", help="Refresh terminal orders too, not just pending ones."),
    market_db: bool = typer.Option(
        True,
        "--market-db/--no-market-db",
        help="Also write latest local RH snapshot/activity/quotes and pull new rh-server runs into ~/.cfo/data/market.db.",
    ),
) -> None:
    """One-shot sync: portfolio + raw trades + order states (+ market DB).

    By default also writes the latest local Robinhood snapshot/activity/
    watchlist quotes into market.db, then runs the incremental rh-server
    schedule sync so remote artifacts are reflected in the same SQLite DB.
    Use ``--no-market-db`` to skip that leg.
    """
    started = time.monotonic()
    try:
        result = portfolio_cmd.run_sync(
            sync_portfolio=portfolio,
            import_rh=import_rh,
            refresh_orders=refresh_orders,
            all_orders=all_orders,
        )
    except RuntimeError as e:
        console.print(f"[red]sync failed:[/red] {e}")
        audit.record(cmd=["cfo", "sync"], result="error",
                     duration_ms=int((time.monotonic() - started) * 1000))
        raise typer.Exit(code=1)

    parts = []
    if portfolio:
        parts.append(f"{result['added']} new + {result['updated']} updated accounts")
    if import_rh:
        parts.append(f"{result['imported_trades']} imported trades")
    if refresh_orders:
        parts.append(f"{result['refreshed_orders']} refreshed orders")
    if not parts:
        parts.append("nothing requested")
    console.print(f"[green]ok[/green] sync complete: " + " ; ".join(parts))

    # Market DB sync is best-effort — never fail the overall sync because
    # of it. Rh-server being unreachable is common (travel, wifi, etc.)
    # and shouldn't block the important portfolio/trades refresh above.
    if market_db:
        try:
            from cfo.market_db.live_sync import sync_live_market_data
            from cfo.market_db.sync import sync_market_data

            live_result = sync_live_market_data(snapshot_payload=result.get("snapshot_payload"))
            console.print(
                f"[green]ok[/green] live-db sync: "
                f"{live_result.account_rows} account rows, "
                f"{live_result.activity_rows} activity rows, "
                f"{live_result.quote_rows} quote rows"
            )
            if live_result.errors:
                console.print(
                    f"[yellow]⚠  live-db sync had {len(live_result.errors)} non-fatal errors[/yellow]"
                )

            db_result = sync_market_data()
            console.print(
                f"[green]ok[/green] market-db sync: "
                f"{db_result.runs_inserted} new runs, "
                f"{db_result.rows_written} rows written"
                + (
                    f", {db_result.runs_skipped_duplicate} skipped"
                    if db_result.runs_skipped_duplicate
                    else ""
                )
                + (
                    f", {db_result.unknown_payloads} unknown payloads — need parser"
                    if db_result.unknown_payloads
                    else ""
                )
            )
            if db_result.errors:
                console.print(
                    f"[yellow]⚠  market-db sync had {len(db_result.errors)} non-fatal errors;[/yellow] "
                    "run `cfo db status` for details"
                )
        except Exception as exc:  # noqa: BLE001 - best-effort by design
            console.print(
                f"[yellow]⚠  market-db sync skipped:[/yellow] {exc}"
            )

    audit.record(cmd=["cfo", "sync"], result="ok",
                 duration_ms=int((time.monotonic() - started) * 1000))


def status_cmd(
    trades_limit: int = typer.Option(5, "--trades-limit", min=1, help="How many recent trades to show."),
    pending_limit: int = typer.Option(10, "--pending-limit", min=1, help="How many pending real orders to show."),
    with_trades: bool = typer.Option(True, "--trades/--no-trades", help="Show recent trades."),
    with_paper: bool = typer.Option(True, "--paper/--no-paper", help="Show paper portfolios."),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", help="table | plain | json"),
) -> None:
    """Unified overview: accounts, strategies, paper, recent trades, pending orders."""
    started = time.monotonic()

    af = core_portfolio.load()
    strategies = core_strategy.list_strategies()
    paper_metas = core_paper.list_all() if with_paper else []
    trades = core_tradebook.load_all()
    recent = trades[-trades_limit:] if with_trades else []

    total = sum(a.balance for a in af.accounts)
    pending = [
        t for t in trades
        if t.mode == TradeMode.real and t.rh_order_id and (t.order_state or "").lower() not in core_tradebook.TERMINAL_ORDER_STATES
    ][-pending_limit:]
    tracked_quotes = _latest_tracked_quotes()
    live_activity = _latest_live_activity(trades_limit)
    payload = {
        "summary": {
            "net_worth": round(total, 2),
            "account_count": len(af.accounts),
            "strategy_count": len(strategies),
            "paper_count": len(paper_metas),
            "pending_order_count": len(pending),
            "recent_trade_count": len(recent),
            "last_updated": af.last_updated,
        },
        "accounts": [
            {
                "id": a.id,
                "type": a.type,
                "broker": a.broker,
                "source": a.source,
                "balance": a.balance,
                "cash": a.cash,
                "holdings": a.holdings,
            }
            for a in af.accounts
        ],
        "strategies": [
            {
                "name": s.name,
                "state": s.state,
                "created_at": s.created_at,
                "paper_portfolio": s.paper_portfolio,
                "live_account": s.live_account,
                "capital_budget": s.capital_budget,
            }
            for s in strategies
        ],
        "paper_portfolios": [
            {
                "id": m.id,
                "kind": m.kind,
                "strategy_ref": m.strategy_ref,
                "capital_start": m.capital_start,
                "capital_current": m.capital_current,
                "created_at": m.created_at,
                "status": m.status,
            }
            for m in paper_metas
        ] if with_paper else [],
        "tracked_quotes": tracked_quotes,
        "live_activity": live_activity,
        "pending_orders": [
            {
                "ts": tr.ts,
                "account_id": tr.account_id,
                "symbol": tr.symbol,
                "side": tr.side,
                "qty": tr.qty,
                "price": tr.price,
                "total": tr.total,
                "strategy": tr.strategy,
                "state": tr.order_state,
                "order_id": tr.rh_order_id,
                "order_updated_at": tr.order_updated_at,
            }
            for tr in pending
        ],
        "recent_trades": [
            {
                "ts": tr.ts,
                "mode": tr.mode,
                "account_id": tr.account_id,
                "symbol": tr.symbol,
                "side": tr.side,
                "qty": tr.qty,
                "price": tr.price,
                "total": tr.total,
                "strategy": tr.strategy,
                "state": tr.order_state,
                "order_id": tr.rh_order_id,
            }
            for tr in recent
        ],
    }

    if format == OutputFormat.plain:
        render_plain(console, payload)
        audit.record(cmd=["cfo", "status"], result="ok",
                     duration_ms=int((time.monotonic() - started) * 1000))
        return
    if format == OutputFormat.json:
        render_json(console, payload)
        audit.record(cmd=["cfo", "status"], result="ok",
                     duration_ms=int((time.monotonic() - started) * 1000))
        return

    console.print(f"[bold]Net Worth Snapshot[/bold]  ${total:,.2f} across {len(af.accounts)} account(s)")

    if af.accounts:
        t = Table(title="Accounts")
        for col in ("ID", "Type", "Broker", "Balance", "Holdings"):
            t.add_column(col)
        for a in af.accounts:
            t.add_row(a.id, a.type.value, a.broker, f"{a.balance:,.2f}", str(len(a.holdings)))
        console.print(t)

    t2 = Table(title=f"Strategies ({len(strategies)})")
    for col in ("Name", "State", "Paper", "Live", "Budget"):
        t2.add_column(col)
    if strategies:
        for s in strategies:
            t2.add_row(
                s.name,
                s.state.value,
                s.paper_portfolio or "-",
                s.live_account or "-",
                f"{s.capital_budget:,.2f}" if s.capital_budget is not None else "-",
            )
    else:
        t2.add_row("-", "-", "-", "-", "-")
    console.print(t2)

    if with_paper:
        t3 = Table(title=f"Paper Portfolios ({len(paper_metas)})")
        for col in ("ID", "Strategy", "Capital", "Status"):
            t3.add_column(col)
        if paper_metas:
            for m in paper_metas:
                t3.add_row(m.id, m.strategy_ref or "-", f"{m.capital_current:,.2f}", m.status)
        else:
            t3.add_row("-", "-", "-", "-")
        console.print(t3)

    t4 = Table(title=f"Pending Orders ({len(pending)})")
    for col in ("TS", "Symbol", "Qty", "State", "OrderID", "Strategy"):
        t4.add_column(col)
    if pending:
        for tr in pending:
            t4.add_row(
                format_local_dt(tr.ts),
                tr.symbol,
                f"{tr.qty:g}",
                tr.order_state or "-",
                tr.rh_order_id or "-",
                tr.strategy or "-",
            )
    else:
        t4.add_row("-", "-", "-", "-", "-", "-")
    console.print(t4)

    if with_trades:
        t5 = Table(title=f"Recent Trades ({len(recent)})")
        for col in ("TS", "Mode", "Symbol", "Side", "Total", "Strategy"):
            t5.add_column(col)
        if recent:
            for tr in recent:
                t5.add_row(
                    format_local_dt(tr.ts),
                    tr.mode.value,
                    tr.symbol,
                    tr.side.value,
                    f"{tr.total:.2f}" if tr.total is not None else "-",
                    tr.strategy or "-",
                )
        else:
            t5.add_row("-", "-", "-", "-", "-", "-")
        console.print(t5)

    if tracked_quotes:
        t6 = Table(title=f"Tracked Quotes ({len(tracked_quotes)})")
        for col in ("Symbol", "Price", "Day %", "Updated"):
            t6.add_column(col)
        for row in tracked_quotes:
            pct = row.get("day_change_pct")
            pct_text = "-" if pct is None else f"{pct * 100:.2f}%"
            price = row.get("current_price")
            price_text = "-" if price is None else f"{price:,.2f}"
            t6.add_row(
                row.get("symbol", "-"),
                price_text,
                pct_text,
                row.get("ts", "-"),
            )
        console.print(t6)

    if live_activity:
        t7 = Table(title=f"Live Activity ({len(live_activity)})")
        for col in ("Created", "Symbol", "Side", "Qty", "Price", "State"):
            t7.add_column(col)
        for row in live_activity:
            price = row.get("price")
            price_text = "-" if price is None else f"{price:,.2f}"
            qty = row.get("quantity")
            qty_text = "-" if qty is None else f"{qty:g}"
            t7.add_row(
                row.get("created_at", "-"),
                row.get("symbol", "-"),
                row.get("side", "-"),
                qty_text,
                price_text,
                row.get("state", "-"),
            )
        console.print(t7)

    audit.record(cmd=["cfo", "status"], result="ok",
                 duration_ms=int((time.monotonic() - started) * 1000))
