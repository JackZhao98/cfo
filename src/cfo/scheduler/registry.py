"""OS detection + backend dispatch."""
import platform

from cfo.scheduler.base import SchedulerBackend


def get_backend() -> SchedulerBackend:
    sys = platform.system()
    if sys == "Darwin":
        from cfo.scheduler.launchd import LaunchdBackend
        return LaunchdBackend()
    if sys == "Linux":
        from cfo.scheduler.systemd import SystemdBackend
        return SystemdBackend()
    if sys == "Windows":
        from cfo.scheduler.schtasks import SchtasksBackend
        return SchtasksBackend()
    raise NotImplementedError(f"unsupported OS: {sys}")
