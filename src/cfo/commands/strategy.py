"""cfo strategy — new / list / status."""
import time

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import strategy as core
from cfo.schemas.strategy import StrategyState
from cfo.util import audit
from cfo.util.render import OutputFormat, render_json, render_plain

console = Console()
strategy_app = typer.Typer(help="Strategy lifecycle management.")


@strategy_app.command("new")
def new(
    name: str = typer.Argument(...),
    template: str = typer.Option("blank", "--template", help="wheel | dca | blank"),
):
    start = time.monotonic()
    try:
        core.new_strategy(name=name, template=template)
    except FileExistsError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "strategy", "new", name], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] created strategy {name} (template: {template})")
    audit.record(cmd=["cfo", "strategy", "new", name], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@strategy_app.command("list")
def list_cmd(
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", help="table | plain | json"),
):
    metas = core.list_strategies()
    payload = {
        "count": len(metas),
        "strategies": metas,
    }
    if not metas:
        if format == OutputFormat.table:
            console.print("[yellow]no strategies yet. run `cfo strategy new <name>`[/yellow]")
        elif format == OutputFormat.plain:
            render_plain(console, payload)
        else:
            render_json(console, payload)
        return
    if format == OutputFormat.plain:
        render_plain(console, payload)
    elif format == OutputFormat.json:
        render_json(console, payload)
    else:
        t = Table(title=f"Strategies ({len(metas)})")
        t.add_column("Name")
        t.add_column("State")
        t.add_column("Created")
        t.add_column("Paper")
        t.add_column("Live")
        t.add_column("Budget")
        for m in metas:
            t.add_row(
                m.name,
                m.state.value,
                str(m.created_at or "-"),
                m.paper_portfolio or "-",
                m.live_account or "-",
                f"{m.capital_budget:,.2f}" if m.capital_budget is not None else "-",
            )
        console.print(t)


@strategy_app.command("status")
def status(
    name: str = typer.Argument(...),
    to: StrategyState = typer.Option(..., "--to"),
):
    start = time.monotonic()
    try:
        core.transition(name, to)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "strategy", "status", name, to.value], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] {name} → {to.value}")
    audit.record(cmd=["cfo", "strategy", "status", name, to.value], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@strategy_app.command("bind-live")
def bind_live(
    name: str = typer.Argument(...),
    account: str = typer.Option(..., "--account", help="Live account id, e.g. rh-individual or rh-roth."),
):
    start = time.monotonic()
    try:
        core.set_live_account(name, account)
    except (FileNotFoundError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "strategy", "bind-live", name, account], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] {name} live_account → {account}")
    audit.record(cmd=["cfo", "strategy", "bind-live", name, account], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@strategy_app.command("clear-live")
def clear_live(name: str = typer.Argument(...)):
    start = time.monotonic()
    try:
        core.set_live_account(name, None)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "strategy", "clear-live", name], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] {name} live_account cleared")
    audit.record(cmd=["cfo", "strategy", "clear-live", name], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@strategy_app.command("set-budget")
def set_budget(
    name: str = typer.Argument(...),
    amount: float = typer.Option(..., "--amount", min=0, help="Capital budget in USD."),
):
    start = time.monotonic()
    try:
        core.set_capital_budget(name, amount)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "strategy", "set-budget", name, str(amount)], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] {name} capital_budget → {amount:,.2f}")
    audit.record(cmd=["cfo", "strategy", "set-budget", name, str(amount)], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@strategy_app.command("clear-budget")
def clear_budget(name: str = typer.Argument(...)):
    start = time.monotonic()
    try:
        core.set_capital_budget(name, None)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "strategy", "clear-budget", name], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] {name} capital_budget cleared")
    audit.record(cmd=["cfo", "strategy", "clear-budget", name], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))
