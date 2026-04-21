"""cfo migrate — one-shot migrations (paths, schema, ...)."""
import shutil
import time
from pathlib import Path

import typer
from rich.console import Console

from cfo.util import audit, paths

console = Console()
migrate_app = typer.Typer(help="One-shot migrations (paths, schema versions).")


def _move_tree(src: Path, dst: Path) -> bool:
    """Move src into dst (merging). Returns True if anything moved."""
    if not src.exists() or not src.is_dir():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.move(str(src), str(dst))
        return True
    # dst exists — merge: move each child, skipping collisions
    moved = False
    for child in list(src.iterdir()):
        target = dst / child.name
        if target.exists():
            console.print(f"[yellow]skip[/yellow] {child} (already exists at {target})")
            continue
        shutil.move(str(child), str(target))
        moved = True
    # If src is now empty, remove it
    try:
        src.rmdir()
    except OSError:
        pass
    return moved


@migrate_app.command("paths")
def paths_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would move, don't actually move."),
):
    """Move legacy data/config dirs to the new ~/.cfo/ layout.

    Legacy → New:
      ~/Developer/Robinhood/data → ~/.cfo/data
      ~/.config/cfo              → ~/.cfo/config

    Idempotent: safe to re-run. Existing destinations are preserved.
    """
    start = time.monotonic()
    new_data = paths.data_dir()
    new_config = paths.config_dir()
    any_moved = False

    for src in paths.LEGACY_DATA_DIRS:
        if src.exists() and src != new_data:
            if dry_run:
                console.print(f"[cyan]would move[/cyan] {src} → {new_data}")
            else:
                console.print(f"moving {src} → {new_data}")
                if _move_tree(src, new_data):
                    any_moved = True

    for src in paths.LEGACY_CONFIG_DIRS:
        if src.exists() and src != new_config:
            if dry_run:
                console.print(f"[cyan]would move[/cyan] {src} → {new_config}")
            else:
                console.print(f"moving {src} → {new_config}")
                if _move_tree(src, new_config):
                    any_moved = True

    if not any_moved and not dry_run:
        console.print("[yellow]nothing to migrate — already on new layout[/yellow]")
    elif not dry_run:
        console.print(f"[green]ok[/green] new data: {new_data}")
        console.print(f"[green]ok[/green] new config: {new_config}")

    audit.record(
        cmd=["cfo", "migrate", "paths"],
        result="ok",
        duration_ms=int((time.monotonic() - start) * 1000),
    )
