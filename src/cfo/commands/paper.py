"""cfo paper — create / list / close."""
import time

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import paper as core
from cfo.schemas.paper import PaperKind
from cfo.util import audit

console = Console()
paper_app = typer.Typer(help="Paper portfolio management.")


@paper_app.command("create")
def create_cmd(
    type_: str = typer.Option(..., "--type", help="strategy | composite"),
    name: str = typer.Option(..., "--name"),
    capital: float = typer.Option(..., "--capital"),
    strategy: str | None = typer.Option(None, "--strategy", help="required if type=strategy"),
):
    start = time.monotonic()
    try:
        kind = PaperKind(type_)
    except ValueError:
        console.print(f"[red]invalid --type: {type_} (use 'strategy' or 'composite')[/red]")
        raise typer.Exit(code=1)
    if kind == PaperKind.strategy and not strategy:
        console.print("[red]--strategy is required for type=strategy[/red]")
        raise typer.Exit(code=1)
    try:
        core.create(kind=kind, pid=name, capital=capital, strategy_ref=strategy)
    except FileExistsError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "paper", "create", name], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] created paper portfolio {name} (${capital:,.2f})")
    audit.record(cmd=["cfo", "paper", "create", name], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))


@paper_app.command("list")
def list_cmd():
    metas = core.list_all()
    if not metas:
        console.print("[yellow]no paper portfolios. run `cfo paper create`[/yellow]")
        return
    t = Table(title=f"Paper Portfolios ({len(metas)})")
    for col in ("ID", "Kind", "Strategy", "Capital Start", "Capital Now", "Status", "Created"):
        t.add_column(col)
    for m in metas:
        t.add_row(
            m.id, m.kind.value, m.strategy_ref or "-",
            f"{m.capital_start:,.2f}", f"{m.capital_current:,.2f}",
            m.status, m.created_at.isoformat(),
        )
    console.print(t)


@paper_app.command("close")
def close_cmd(pid: str = typer.Argument(...)):
    start = time.monotonic()
    try:
        core.close(pid)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(cmd=["cfo", "paper", "close", pid], result="error",
                     duration_ms=int((time.monotonic() - start) * 1000))
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] closed paper portfolio {pid}")
    audit.record(cmd=["cfo", "paper", "close", pid], result="ok",
                 duration_ms=int((time.monotonic() - start) * 1000))
