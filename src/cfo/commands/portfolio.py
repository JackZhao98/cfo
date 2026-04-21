"""cfo portfolio — show / update / sync."""
import time
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import portfolio as core
from cfo.core import rh_bridge
from cfo.schemas.portfolio import Account, AccountSource, AccountType
from cfo.util import audit

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
    account_number = str(rh_a.get("account_number", ""))
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


@portfolio_app.command("show")
def show():
    """Display all accounts and holdings."""
    start = time.monotonic()
    af = core.load()
    if not af.accounts:
        console.print("[yellow]no accounts configured. Run `cfo init` to start.[/yellow]")
        audit.record(cmd=["cfo", "portfolio", "show"], result="ok",
                     duration_ms=int((time.monotonic() - start) * 1000))
        return
    table = Table(title=f"Accounts (last_updated: {af.last_updated.isoformat(timespec='seconds')})")
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


@portfolio_app.command("sync")
def sync():
    """Pull current RH positions via `rh account snapshot --json` and upsert accounts."""
    start = time.monotonic()
    try:
        payload = rh_bridge.snapshot()
    except RuntimeError as e:
        console.print(f"[red]rh sync failed: {e}[/red]")
        audit.record(cmd=["cfo", "portfolio", "sync"], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)

    af = core.load()
    existing_by_id = {a.id: a for a in af.accounts}
    new_rh_accounts: list[Account] = []
    updated = 0
    added = 0

    for rh_a in payload.get("accounts", []):
        acc = _rh_account_to_cfo(rh_a)
        if acc.id in existing_by_id:
            updated += 1
        else:
            added += 1
        new_rh_accounts.append(acc)

    # keep non-rh accounts intact
    preserved = [a for a in af.accounts if a.source != AccountSource.rh_sync]
    new_accounts = preserved + new_rh_accounts

    new_af = af.model_copy(update={
        "accounts": new_accounts,
        "last_updated": datetime.now(timezone.utc),
    })
    core.save(new_af)
    console.print(f"[green]ok[/green] synced {added} new + {updated} updated RH accounts")
    audit.record(cmd=["cfo", "portfolio", "sync"], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))
