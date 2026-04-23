"""cfo portfolio — show / update / sync."""
import time
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import portfolio as core
from cfo.core import rh_bridge
from cfo.core import tradebook as core_tradebook
from cfo.schemas.portfolio import Account, AccountSource, AccountType
from cfo.util import audit
from cfo.util.render import OutputFormat, format_local_dt, render_json, render_plain

console = Console()
portfolio_app = typer.Typer(help="Portfolio management (accounts, holdings).")


_RH_TYPE_MAP: dict[str, AccountType] = {
    "individual": AccountType.taxable,
    "ira_roth": AccountType.roth_ira,
    "ira_traditional": AccountType.traditional_ira,
}


# Stable CFO account IDs for well-known RH account types.
# Fallback: rh-<account_number> if type unrecognized (ensures uniqueness).
_RH_ID_MAP: dict[str, str] = {
    "individual": "rh-individual",
    "ira_roth": "rh-roth",
    "ira_traditional": "rh-traditional",
}


def _rh_account_to_cfo(rh_a: dict) -> Account:
    """Map rh `account snapshot --format json` account shape to cfo Account."""
    rh_type = str(rh_a.get("brokerage_account_type", "")).lower()
    management_type = str(rh_a.get("management_type", "")).lower()
    account_number = str(rh_a.get("account_number", ""))
    if rh_type == "individual" and management_type == "managed":
        cfo_id = "rh-managed-individual"
    else:
        cfo_id = _RH_ID_MAP.get(rh_type) or f"rh-{account_number}"
    atype = _RH_TYPE_MAP.get(rh_type, AccountType.other)
    balance = float(rh_a.get("portfolio_value", 0))
    cash = float(rh_a.get("cash", 0))
    holdings = [
        {
            "symbol": h.get("symbol", ""),
            "qty": float(h.get("shares", 0)),
            "cost_basis": float(h.get("avg_cost", 0)),
        }
        for h in rh_a.get("holdings", [])
    ]
    return Account(
        id=cfo_id,
        type=atype,
        broker="robinhood",
        source=AccountSource.rh_sync,
        balance=balance,
        cash=cash,
        holdings=holdings,
    )


def run_sync(
    *,
    sync_portfolio: bool = True,
    import_rh: bool = True,
    refresh_orders: bool = True,
    all_orders: bool = False,
) -> dict[str, int]:
    payload = {"accounts": []}
    af = core.load()
    added = 0
    updated = 0

    if sync_portfolio:
        payload = rh_bridge.snapshot()
        existing_by_id = {a.id: a for a in af.accounts}
        new_rh_accounts: list[Account] = []
        for rh_a in payload.get("accounts", []):
            acc = _rh_account_to_cfo(rh_a)
            if acc.id in existing_by_id:
                updated += 1
            else:
                added += 1
            new_rh_accounts.append(acc)

        preserved = [a for a in af.accounts if a.source != AccountSource.rh_sync]
        new_accounts = preserved + new_rh_accounts
        new_af = af.model_copy(update={
            "accounts": new_accounts,
            "last_updated": datetime.now(timezone.utc),
        })
        core.save(new_af)

    imported_trades = core_tradebook.import_rh_trades_log() if import_rh else 0
    refreshed_orders = 0
    if refresh_orders:
        refreshed_orders = core_tradebook.sync_order_details(
            rh_bridge.order,
            pending_only=not all_orders,
        )

    return {
        "added": added,
        "updated": updated,
        "imported_trades": imported_trades,
        "refreshed_orders": refreshed_orders,
        "snapshot_payload": payload if sync_portfolio else None,
    }


@portfolio_app.command("show")
def show(
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", help="table | plain | json"),
):
    """Display all accounts and holdings."""
    start = time.monotonic()
    af = core.load()
    payload = {
        "last_updated": af.last_updated,
        "count": len(af.accounts),
        "accounts": af.accounts,
    }
    if not af.accounts:
        if format == OutputFormat.table:
            console.print("[yellow]no accounts configured. Run `cfo init` to start.[/yellow]")
        elif format == OutputFormat.plain:
            render_plain(console, payload)
        else:
            render_json(console, payload)
        audit.record(cmd=["cfo", "portfolio", "show"], result="ok",
                     duration_ms=int((time.monotonic() - start) * 1000))
        return
    if format == OutputFormat.plain:
        render_plain(console, payload)
    elif format == OutputFormat.json:
        render_json(console, payload)
    else:
        table = Table(title=f"Accounts (last_updated: {format_local_dt(af.last_updated, timespec='seconds')})")
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Broker")
        table.add_column("Source")
        table.add_column("Balance", justify="right")
        table.add_column("Holdings", justify="right")
        for a in af.accounts:
            table.add_row(
                a.id,
                a.type.value,
                a.broker,
                a.source.value,
                f"{a.balance:,.2f}",
                str(len(a.holdings)),
            )
        console.print(table)
    audit.record(cmd=["cfo", "portfolio", "show"], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@portfolio_app.command("update")
def update(
    account: str = typer.Option(..., "--account", "-a", help="Account id (e.g. chase, rh-roth)."),
    balance: float = typer.Option(..., "--balance", "-b", help="New balance USD."),
):
    """Manually update an account balance (for external accounts like Chase)."""
    start = time.monotonic()
    try:
        core.update_balance(account_id=account, balance=balance)
    except KeyError:
        console.print(f"[red]account not found: {account}[/red]")
        audit.record(
            cmd=["cfo", "portfolio", "update", "--account", account, "--balance", str(balance)],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] {account} balance → {balance:,.2f}")
    audit.record(
        cmd=["cfo", "portfolio", "update", "--account", account, "--balance", str(balance)],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@portfolio_app.command("add")
def add(
    account: str = typer.Option(..., "--account", "-a", help="New account id (e.g. chase, fidelity-taxable)."),
    type_: AccountType = typer.Option(..., "--type", help="Account type."),
    balance: float = typer.Option(..., "--balance", "-b", help="Current balance USD."),
    broker: str = typer.Option(..., "--broker", help="Broker or institution name."),
    cash: float | None = typer.Option(None, "--cash", help="Optional cash balance USD."),
):
    """Add a non-Robinhood/manual account to accounts.json."""
    start = time.monotonic()
    default_cash = balance if type_ in {AccountType.checking, AccountType.savings, AccountType.hysa} else 0.0
    new_account = Account(
        id=account,
        type=type_,
        broker=broker,
        source=AccountSource.manual,
        balance=balance,
        cash=default_cash if cash is None else cash,
    )
    try:
        core.add_account(new_account)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "portfolio", "add", "--account", account],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] added account {account} ({broker})")
    audit.record(
        cmd=["cfo", "portfolio", "add", "--account", account],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@portfolio_app.command("sync")
def sync():
    """Pull current RH positions via `rh account snapshot --json` and upsert accounts."""
    start = time.monotonic()
    try:
        result = run_sync(sync_portfolio=True, import_rh=True, refresh_orders=True, all_orders=False)
    except RuntimeError as e:
        console.print(f"[red]rh sync failed: {e}[/red]")
        audit.record(cmd=["cfo", "portfolio", "sync"], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(
        f"[green]ok[/green] synced {result['added']} new + {result['updated']} updated RH accounts"
        f" ; imported {result['imported_trades']} trade(s)"
        f" ; refreshed {result['refreshed_orders']} order(s)"
    )
    audit.record(cmd=["cfo", "portfolio", "sync"], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))
