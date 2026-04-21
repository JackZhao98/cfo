"""Windows schtasks backend — STUB filled in C.3."""
from cfo.schemas.schedule import ScheduledTask


class SchtasksBackend:
    def install(self, task: ScheduledTask) -> None:
        raise NotImplementedError

    def uninstall(self, task_id: str) -> None:
        raise NotImplementedError

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        raise NotImplementedError

    def list_native(self) -> list[str]:
        raise NotImplementedError

    def run_once(self, task: ScheduledTask) -> int:
        raise NotImplementedError
