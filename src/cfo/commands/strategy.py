"""cfo strategy — new / list / status."""
import time

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import strategy as core
from cfo.schemas.strategy import StrategyState
from cfo.util import audit

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
def list_cmd():
    metas = core.list_strategies()
    if not metas:
        console.print("[yellow]no strategies yet. run `cfo strategy new <name>`[/yellow]")
        return
    t = Table(title=f"Strategies ({len(metas)})")
    t.add_column("Name")
    t.add_column("State")
    t.add_column("Created")
    t.add_column("Paper")
    for m in metas:
        t.add_row(m.name, m.state.value, str(m.created_at or "-"), m.paper_portfolio or "-")
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
