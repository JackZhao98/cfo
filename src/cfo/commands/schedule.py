"""cfo schedule — cross-platform task management."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

from cfo.core import rh_server
from cfo.core import schedule as core
from cfo.schemas.schedule import ScheduledTask, SchedulesFile
from cfo.scheduler import registry
from cfo.util import audit, atomic, yaml_io

console = Console()
schedule_app = typer.Typer(help="Cross-platform scheduled tasks.")


def _manifest_payload(schedules: SchedulesFile) -> dict:
    return schedules.model_dump(mode="json", exclude_none=True)


def _detect_format(path: Path | None, format_: str | None) -> Literal["json", "yaml"]:
    if format_:
        if format_ not in {"json", "yaml"}:
            raise ValueError(f"unsupported format: {format_}")
        return format_  # type: ignore[return-value]
    if path and path.suffix.lower() in {".yaml", ".yml"}:
        return "yaml"
    return "json"


def _render_manifest_text(schedules: SchedulesFile, format_: Literal["json", "yaml"]) -> str:
    payload = _manifest_payload(schedules)
    if format_ == "yaml":
        return yaml_io.yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _write_manifest(path: Path, schedules: SchedulesFile, format_: Literal["json", "yaml"]) -> None:
    payload = _manifest_payload(schedules)
    if format_ == "yaml":
        yaml_io.dump_yaml(path, payload)
        return
    atomic.write_json(path, payload)


def _load_manifest(path: Path, format_: str | None) -> SchedulesFile:
    chosen = _detect_format(path, format_)
    if chosen == "yaml":
        data = yaml_io.load_yaml(path)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    return SchedulesFile.model_validate(data)


def _ensure_unique_ids(tasks: list[ScheduledTask]) -> None:
    seen: set[str] = set()
    dupes: set[str] = set()
    for task in tasks:
        if task.id in seen:
            dupes.add(task.id)
        seen.add(task.id)
    if dupes:
        dupes_str = ", ".join(sorted(dupes))
        raise ValueError(f"manifest has duplicate task ids: {dupes_str}")


def _install_task(backend, task: ScheduledTask) -> None:
    backend.install(task)
    if not task.enabled:
        backend.set_enabled(task.id, False)


def _remote_client() -> rh_server.RHServerClient:
    cfg = rh_server.load_config(require=True)
    assert cfg is not None
    if not cfg.base_url or not cfg.api_key:
        raise rh_server.RHServerError("RH Server config missing base_url/api_key")
    return rh_server.RHServerClient(cfg.base_url, cfg.api_key)


def _mode() -> Literal["local", "remote"]:
    return rh_server.get_mode()


def _refresh_remote_index(client: rh_server.RHServerClient | None = None) -> Path:
    client = client or _remote_client()
    _, path = rh_server.refresh_schedule_index(client)
    return path


def _remote_schedules_to_file(schedules: list[dict]) -> tuple[SchedulesFile, list[str]]:
    tasks: list[ScheduledTask] = []
    skipped: list[str] = []
    for item in schedules:
        try:
            tasks.append(rh_server.remote_schedule_to_task(item))
        except rh_server.RHServerError:
            skipped.append(str(item.get("name") or "<unknown>"))
    incoming = SchedulesFile(schema_version=1, tasks=tasks)
    _ensure_unique_ids(incoming.tasks)
    return incoming, skipped


def _list_local_tasks(tasks: list[ScheduledTask]) -> None:
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


def _list_remote_schedules(schedules: list[dict]) -> None:
    if not schedules:
        console.print("[yellow]no remote schedules[/yellow]")
        return
    t = Table(title=f"RH Server schedules ({len(schedules)})")
    for col in ("Name", "Enabled", "TZ", "Trigger", "Executor", "Job", "Next Run"):
        t.add_column(col)
    for item in schedules:
        trigger = item.get("trigger") or {}
        executor = item.get("executor") or {}
        job = item.get("job") or {}
        t.add_row(
            str(item.get("name") or ""),
            "yes" if item.get("enabled", True) else "no",
            str(item.get("timezone") or ""),
            str(trigger.get("expr") or ""),
            f"{executor.get('type') or ''}:{executor.get('target') or ''}".rstrip(":"),
            str(job.get("type") or ""),
            str(item.get("next_run_at") or ""),
        )
    console.print(t)


def _get_remote_schedule(client: rh_server.RHServerClient, task_id: str) -> dict:
    try:
        return client.get_schedule(task_id)
    except rh_server.RHServerError as e:
        raise typer.Exit(1) from e


def _apply_imported_tasks(
    incoming: SchedulesFile,
    *,
    replace: bool,
    install: bool,
    source_label: str,
    cmd: list[str],
    start: float,
) -> None:
    current = core.load()
    incoming_ids = {task.id for task in incoming.tasks}
    existing_ids = {task.id for task in current.tasks}
    duplicates = sorted(incoming_ids & existing_ids)
    if duplicates and not replace:
        console.print(
            f"[red]task(s) already exist: {', '.join(duplicates)}; "
            "use --replace to overwrite[/red]"
        )
        audit.record(
            cmd=cmd,
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)

    backend = registry.get_backend() if install else None
    installed_new_ids: list[str] = []
    try:
        if replace:
            if backend:
                for task in current.tasks:
                    try:
                        backend.uninstall(task.id)
                    except Exception:
                        pass
            core.save(incoming)
            if backend:
                for task in incoming.tasks:
                    _install_task(backend, task)
                    installed_new_ids.append(task.id)
        else:
            for task in incoming.tasks:
                core.add(task)
            if backend:
                for task in incoming.tasks:
                    _install_task(backend, task)
                    installed_new_ids.append(task.id)
    except Exception as e:
        if replace:
            core.save(current)
            if backend:
                for task_id in installed_new_ids:
                    try:
                        backend.uninstall(task_id)
                    except Exception:
                        pass
                for task in current.tasks:
                    try:
                        _install_task(backend, task)
                    except Exception:
                        pass
        else:
            for task in incoming.tasks:
                try:
                    core.remove(task.id)
                except KeyError:
                    pass
            if backend:
                for task_id in installed_new_ids:
                    try:
                        backend.uninstall(task_id)
                    except Exception:
                        pass
        console.print(f"[red]import failed: {e}[/red]")
        audit.record(
            cmd=cmd,
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)

    console.print(f"[green]ok[/green] imported {len(incoming.tasks)} task(s) from {source_label}")
    audit.record(
        cmd=cmd,
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


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
    if _mode() == "remote":
        try:
            client = _remote_client()
            payload = rh_server.scheduled_task_to_remote(task)
            client.upsert_schedule(task.id, payload)
            _refresh_remote_index(client)
        except rh_server.RHServerError as e:
            console.print(f"[red]{e}[/red]")
            audit.record(
                cmd=["cfo", "schedule", "add", id],
                result="error",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            raise typer.Exit(1)
        console.print(f"[green]ok[/green] remote schedule {id} @ '{cron}'")
        audit.record(
            cmd=["cfo", "schedule", "add", id],
            result="ok",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        return
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
    if _mode() == "remote":
        try:
            client = _remote_client()
            schedules = client.list_schedules()
            rh_server.write_schedule_index_markdown(schedules)
        except rh_server.RHServerError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        _list_remote_schedules(schedules)
        return
    _list_local_tasks(core.load().tasks)


@schedule_app.command("export")
def export_cmd(
    file: Path | None = typer.Option(None, "--file"),
    format_: str | None = typer.Option(None, "--format", help="json | yaml"),
):
    """Export schedules SSOT as a portable JSON/YAML manifest."""
    try:
        chosen = _detect_format(file, format_)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if _mode() == "remote":
        try:
            client = _remote_client()
            schedules, skipped = _remote_schedules_to_file(client.list_schedules())
        except rh_server.RHServerError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        if skipped:
            console.print(f"[yellow]skipped {len(skipped)} non-CFO remote schedule(s): {', '.join(skipped)}[/yellow]")
    else:
        schedules = core.load()
    if file:
        _write_manifest(file, schedules, chosen)
        console.print(f"[green]ok[/green] exported {len(schedules.tasks)} task(s) to {file}")
        return
    typer.echo(_render_manifest_text(schedules, chosen), nl=False)


@schedule_app.command("import")
def import_cmd(
    file: Path = typer.Option(..., "--file", exists=True, dir_okay=False, readable=True),
    format_: str | None = typer.Option(None, "--format", help="json | yaml"),
    replace: bool = typer.Option(False, "--replace", help="Replace existing schedules before import."),
    install: bool = typer.Option(True, "--install/--no-install", help="Install imported tasks into the OS scheduler."),
):
    """Import schedules from a portable JSON/YAML manifest."""
    start = time.monotonic()
    try:
        incoming = _load_manifest(file, format_)
        _ensure_unique_ids(incoming.tasks)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "schedule", "import", str(file)],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)

    if _mode() == "remote":
        try:
            client = _remote_client()
            if replace:
                current_remote, _ = _remote_schedules_to_file(client.list_schedules())
                for task in current_remote.tasks:
                    client.delete_schedule(task.id)
            for task in incoming.tasks:
                client.upsert_schedule(task.id, rh_server.scheduled_task_to_remote(task))
            _refresh_remote_index(client)
        except rh_server.RHServerError as e:
            console.print(f"[red]{e}[/red]")
            audit.record(
                cmd=["cfo", "schedule", "import", str(file)],
                result="error",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            raise typer.Exit(1)
        console.print(f"[green]ok[/green] imported {len(incoming.tasks)} task(s) to RH Server")
        audit.record(
            cmd=["cfo", "schedule", "import", str(file)],
            result="ok",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        return

    _apply_imported_tasks(
        incoming,
        replace=replace,
        install=install,
        source_label=str(file),
        cmd=["cfo", "schedule", "import", str(file)],
        start=start,
    )


@schedule_app.command("remote-set")
def remote_set_cmd(
    server: str = typer.Option(..., "--server", help="RH Server base URL."),
    api_key: str = typer.Option(..., "--api-key", help="RH Server API key."),
):
    cfg = rh_server.save_config(server, api_key)
    console.print(
        f"[green]ok[/green] saved RH Server config {cfg.base_url} "
        f"(key {rh_server.mask_api_key(cfg.api_key)})"
    )


@schedule_app.command("connect")
def connect_cmd(
    server: str = typer.Option(..., "--server", help="RH Server base URL."),
    api_key: str = typer.Option(..., "--api-key", help="RH Server API key."),
):
    cfg = rh_server.save_config(server, api_key, mode="remote")
    try:
        _refresh_remote_index(rh_server.RHServerClient(cfg.base_url or "", cfg.api_key or ""))
    except rh_server.RHServerError:
        pass
    console.print(
        f"[green]ok[/green] connected schedule mode to RH Server {cfg.base_url} "
        f"(key {rh_server.mask_api_key(cfg.api_key or '')})"
    )


@schedule_app.command("disconnect")
def disconnect_cmd():
    cfg = rh_server.save_mode("local")
    console.print("[green]ok[/green] schedule mode set to local")
    if cfg.base_url:
        console.print(f"[dim]saved RH Server config retained: {cfg.base_url}[/dim]")


@schedule_app.command("mode")
def mode_cmd(
    to: str | None = typer.Argument(None),
):
    if to is None:
        cfg = rh_server.load_config(require=False)
        mode = rh_server.get_mode()
        t = Table()
        t.add_column("Field")
        t.add_column("Value")
        t.add_row("mode", mode)
        if cfg and cfg.base_url:
            t.add_row("server", cfg.base_url)
        console.print(t)
        return
    if to not in {"local", "remote"}:
        console.print(f"[red]unsupported mode: {to}[/red]")
        raise typer.Exit(1)
    try:
        cfg = rh_server.save_mode(to)  # type: ignore[arg-type]
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]ok[/green] schedule mode set to {cfg.mode}")
    if cfg.mode == "remote" and cfg.base_url:
        console.print(f"[dim]{cfg.base_url}[/dim]")


@schedule_app.command("remote-show")
def remote_show_cmd():
    cfg = rh_server.load_config(require=False)
    if cfg is None:
        console.print("[yellow]RH Server not configured[/yellow]")
        raise typer.Exit(1)
    t = Table()
    t.add_column("Field")
    t.add_column("Value")
    t.add_row("mode", cfg.mode)
    t.add_row("server", cfg.base_url)
    t.add_row("api_key", rh_server.mask_api_key(cfg.api_key or ""))
    console.print(t)


@schedule_app.command("remote-list")
def remote_list_cmd():
    try:
        client = _remote_client()
        schedules = client.list_schedules()
        rh_server.write_schedule_index_markdown(schedules)
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    _list_remote_schedules(schedules)


@schedule_app.command("push")
def push_cmd(
    id: str | None = typer.Option(None, "--id", help="Only push one local task id."),
    executor_type: str = typer.Option("worker", "--executor-type", help="Remote executor type."),
    executor_target: str = typer.Option("cfo", "--executor-target", help="Remote executor target."),
):
    try:
        client = _remote_client()
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    tasks = core.load().tasks
    if id:
        tasks = [task for task in tasks if task.id == id]
        if not tasks:
            console.print(f"[red]task not found: {id}[/red]")
            raise typer.Exit(1)
    if not tasks:
        console.print("[yellow]no local schedules to push[/yellow]")
        return
    try:
        for task in tasks:
            payload = rh_server.scheduled_task_to_remote(
                task,
                executor_type=executor_type,
                executor_target=executor_target,
            )
            client.upsert_schedule(task.id, payload)
        _refresh_remote_index(client)
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]ok[/green] pushed {len(tasks)} schedule(s) to RH Server")


@schedule_app.command("pull")
def pull_cmd(
    replace: bool = typer.Option(False, "--replace", help="Replace local schedules before import."),
    install: bool = typer.Option(False, "--install/--no-install", help="Install pulled tasks into the OS scheduler."),
):
    start = time.monotonic()
    try:
        client = _remote_client()
        schedules = client.list_schedules()
        tasks: list[ScheduledTask] = []
        skipped: list[str] = []
        for item in schedules:
            try:
                tasks.append(rh_server.remote_schedule_to_task(item))
            except rh_server.RHServerError:
                skipped.append(str(item.get("name") or "<unknown>"))
        incoming = SchedulesFile(schema_version=1, tasks=tasks)
        _ensure_unique_ids(incoming.tasks)
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        audit.record(
            cmd=["cfo", "schedule", "pull"],
            result="error",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise typer.Exit(1)

    _apply_imported_tasks(
        incoming,
        replace=replace,
        install=install,
        source_label="RH Server",
        cmd=["cfo", "schedule", "pull"],
        start=start,
    )
    if skipped:
        console.print(f"[yellow]skipped {len(skipped)} non-CFO remote schedule(s): {', '.join(skipped)}[/yellow]")


@schedule_app.command("pause")
def pause(task_id: str = typer.Argument(...)):
    start = time.monotonic()
    if _mode() == "remote":
        try:
            client = _remote_client()
            schedule = client.get_schedule(task_id)
            schedule["enabled"] = False
            client.upsert_schedule(task_id, schedule)
            _refresh_remote_index(client)
        except rh_server.RHServerError as e:
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
        return
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
    if _mode() == "remote":
        try:
            client = _remote_client()
            schedule = client.get_schedule(task_id)
            schedule["enabled"] = True
            client.upsert_schedule(task_id, schedule)
            _refresh_remote_index(client)
        except rh_server.RHServerError as e:
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
        return
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
    if _mode() == "remote":
        try:
            client = _remote_client()
            client.delete_schedule(task_id)
            _refresh_remote_index(client)
        except rh_server.RHServerError as e:
            console.print(f"[red]{e}[/red]")
            audit.record(
                cmd=["cfo", "schedule", "remove", task_id],
                result="error",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            raise typer.Exit(1)
        console.print(f"[green]ok[/green] removed {task_id}")
        audit.record(
            cmd=["cfo", "schedule", "remove", task_id],
            result="ok",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        return
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
    if _mode() == "remote":
        try:
            client = _remote_client()
            run = client.enqueue_schedule(task_id)
        except rh_server.RHServerError as e:
            console.print(f"[red]{e}[/red]")
            audit.record(
                cmd=["cfo", "schedule", "run", task_id],
                result="error",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            raise typer.Exit(1)
        console.print(
            f"[green]ok[/green] enqueued {task_id} "
            f"(run {run.get('id') or '<unknown>'})"
        )
        audit.record(
            cmd=["cfo", "schedule", "run", task_id],
            result="ok",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        return
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


@schedule_app.command("runs")
def runs_cmd(
    task_id: str = typer.Argument(...),
    limit: int = typer.Option(10, "--limit", min=1, max=200),
):
    if _mode() != "remote":
        console.print("[red]schedule runs is only available in remote mode[/red]")
        raise typer.Exit(1)
    try:
        client = _remote_client()
        runs = client.list_schedule_runs(task_id, limit=limit)
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if not runs:
        console.print(f"[yellow]no runs for schedule {task_id}[/yellow]")
        return
    t = Table(title=f"Runs for {task_id} ({len(runs)})")
    for col in ("Run ID", "Created", "Status", "Worker", "Job Type"):
        t.add_column(col)
    for run in runs:
        t.add_row(
            str(run.get("id") or ""),
            str(run.get("created_at") or ""),
            str(run.get("status") or ""),
            str(run.get("worker_name") or ""),
            str(run.get("job_type") or ""),
        )
    console.print(t)


@schedule_app.command("refresh")
def refresh_cmd():
    if _mode() != "remote":
        console.print("[red]schedule refresh is only available in remote mode[/red]")
        raise typer.Exit(1)
    try:
        path = _refresh_remote_index()
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]ok[/green] refreshed remote schedule index: {path}")


@schedule_app.command("run-show")
def run_show_cmd(run_id: str = typer.Argument(...)):
    if _mode() != "remote":
        console.print("[red]schedule run-show is only available in remote mode[/red]")
        raise typer.Exit(1)
    try:
        client = _remote_client()
        detail = client.get_run(run_id)
    except rh_server.RHServerError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    run = detail.get("run") or {}
    artifacts = detail.get("artifacts") or {}
    summary = Table()
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("run_id", str(run.get("id") or ""))
    summary.add_row("schedule", str(run.get("schedule_name") or run.get("schedule_id") or ""))
    summary.add_row("status", str(run.get("status") or ""))
    summary.add_row("created_at", str(run.get("created_at") or ""))
    summary.add_row("worker", str(run.get("worker_name") or ""))
    console.print(summary)
    if artifacts:
        typer.echo(json.dumps(artifacts, indent=2, ensure_ascii=False))
