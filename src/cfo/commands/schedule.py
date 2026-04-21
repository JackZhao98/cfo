"""cfo schedule — cross-platform task management."""
import time
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import schedule as core
from cfo.schemas.schedule import ScheduledTask
from cfo.scheduler import registry
from cfo.util import audit

console = Console()
schedule_app = typer.Typer(help="Cross-platform scheduled tasks.")


@schedule_app.command("add")
def add(
    id: str = typer.Option(..., "--id"),
    cron: str = typer.Option(..., "--cron"),
    cmd: list[str] = typer.Option(
        ..., "--cmd", help="Command tokens; repeat --cmd per token"
    ),
    description: str = typer.Option("", "--description"),
    tz: str = typer.Option("America/Los_Angeles", "--timezone"),
):
    start = time.monotonic()
    task = ScheduledTask(
        id=id,
        cron=cron,
        command=cmd,
        description=description,
        timezone=tz,
        created_at=datetime.now(timezone.utc),
    )
    try:
        core.add(task)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "schedule", "add", id],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)
    try:
        registry.get_backend().install(task)
    except Exception as e:
        console.print(f"[red]backend install failed: {e}[/red]")
        core.remove(id)
        audit.record(
            cmd=["cfo", "schedule", "add", id],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)
    console.print(f"[green]ok[/green] scheduled {id} @ '{cron}'")
    audit.record(
        cmd=["cfo", "schedule", "add", id],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@schedule_app.command("list")
def list_cmd():
    tasks = core.load().tasks
    if not tasks:
        console.print("[yellow]no scheduled tasks. run `cfo schedule add`[/yellow]")
        return
    t = Table(title=f"Scheduled tasks ({len(tasks)})")
    for col in ("ID", "Enabled", "Cron", "TZ", "Command", "Description"):
        t.add_column(col)
    for task in tasks:
        t.add_row(
            task.id,
            "yes" if task.enabled else "no",
            task.cron,
            task.timezone,
            " ".join(task.command),
            task.description,
        )
    console.print(t)


@schedule_app.command("pause")
def pause(task_id: str = typer.Argument(...)):
    start = time.monotonic()
    try:
        core.set_enabled(task_id, False)
        registry.get_backend().set_enabled(task_id, False)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "schedule", "pause", task_id],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)
    console.print(f"[green]ok[/green] paused {task_id}")
    audit.record(
        cmd=["cfo", "schedule", "pause", task_id],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@schedule_app.command("resume")
def resume(task_id: str = typer.Argument(...)):
    start = time.monotonic()
    try:
        core.set_enabled(task_id, True)
        registry.get_backend().set_enabled(task_id, True)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "schedule", "resume", task_id],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)
    console.print(f"[green]ok[/green] resumed {task_id}")
    audit.record(
        cmd=["cfo", "schedule", "resume", task_id],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@schedule_app.command("remove")
def remove(task_id: str = typer.Argument(...)):
    start = time.monotonic()
    try:
        core.remove(task_id)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "schedule", "remove", task_id],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)
    try:
        registry.get_backend().uninstall(task_id)
    except Exception:
        # native config may not exist — treat as acceptable
        pass
    console.print(f"[green]ok[/green] removed {task_id}")
    audit.record(
        cmd=["cfo", "schedule", "remove", task_id],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@schedule_app.command("run")
def run_cmd(task_id: str = typer.Argument(...)):
    """Run task immediately (for debug/verify)."""
    start = time.monotonic()
    try:
        task = core.get(task_id)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "schedule", "run", task_id],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)
    rc = registry.get_backend().run_once(task)
    result = "ok" if rc == 0 else "error"
    color = "green" if rc == 0 else "red"
    console.print(f"[{color}]exit {rc}[/{color}]")
    audit.record(
        cmd=["cfo", "schedule", "run", task_id],
        result=result,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
    if rc != 0:
        raise typer.Exit(rc)
