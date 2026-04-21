"""cfo portfolio — show / update / sync."""
import time

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import portfolio as core
from cfo.util import audit

console = Console()
portfolio_app = typer.Typer(help="Portfolio management (accounts, holdings).")


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
    """Pull current RH positions via `rh account snapshot --json`.

    Stub — writes no data yet; full impl in Phase B once rh JSON output schema stabilizes.
    """
    console.print(
        "[yellow]sync stub — full implementation deferred to Phase B "
        "(after rh snapshot JSON output is stable).[/yellow]"
    )
