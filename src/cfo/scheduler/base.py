"""Scheduler backend Protocol.

Each OS backend translates a ScheduledTask into native config and registers
it with the OS scheduler (launchd/systemd/schtasks).
"""
from typing import Protocol

from cfo.schemas.schedule import ScheduledTask


class SchedulerBackend(Protocol):
    def install(self, task: ScheduledTask) -> None:
        """Register task with OS (create native config + load)."""
        ...

    def uninstall(self, task_id: str) -> None:
        """Unregister + remove native config."""
        ...

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        """Pause/resume without removing."""
        ...

    def list_native(self) -> list[str]:
        """Return list of task IDs currently registered with the OS."""
        ...

    def run_once(self, task: ScheduledTask) -> int:
        """Run task.command synchronously, return exit code."""
        ...
