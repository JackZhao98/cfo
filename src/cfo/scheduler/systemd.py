"""Linux systemd user timer backend."""
import subprocess
from pathlib import Path

from cfo.schemas.schedule import ScheduledTask
from cfo.util import paths


PREFIX = "cfo-"

_DOW_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _parse_field(field: str, valid_range: range) -> list[int]:
    """Parse a single cron field: '*' | 'A' | 'A,B,C' | 'A-B'."""
    if field == "*":
        return [-1]  # sentinel meaning "any"
    out: list[int] = []
    for part in field.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    for v in out:
        if v not in valid_range:
            raise ValueError(f"value {v} out of range {valid_range}")
    return out


def cron_to_oncalendar(cron: str) -> str:
    """Translate standard 5-field cron to a systemd OnCalendar expression.

    Only supports: explicit minute/hour (no '*'), optional DOW list/range.
    day-of-month and month must be '*'.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(f"cron must have 5 fields: {cron!r}")
    m, h, dom, mon, dow = parts
    if m == "*" or h == "*":
        raise ValueError("minute and hour must be specific values (no '*')")
    if dom != "*" or mon != "*":
        raise ValueError("day-of-month and month must be '*'")
    minutes = _parse_field(m, range(0, 60))
    hours = _parse_field(h, range(0, 24))
    dows = _parse_field(dow, range(0, 8))  # cron allows 0-7 (both 0 and 7 = Sunday)

    day_part = "*"
    if dows != [-1]:
        norm = sorted({0 if d == 7 else d for d in dows})
        day_part = ",".join(_DOW_NAMES[d] for d in norm)
    time_part = ",".join(f"{hh:02d}:{mm:02d}" for hh in hours for mm in minutes)
    if day_part == "*":
        return f"*-*-* {time_part}:00"
    return f"{day_part} *-*-* {time_part}:00"


def _service_path(task_id: str) -> Path:
    return paths.systemd_user_dir() / f"{PREFIX}{task_id}.service"


def _timer_path(task_id: str) -> Path:
    return paths.systemd_user_dir() / f"{PREFIX}{task_id}.timer"


def _systemctl(*args: str) -> int:
    r = subprocess.run(
        ["systemctl", "--user", *args], capture_output=True, text=True
    )
    return r.returncode


class SystemdBackend:
    def install(self, task: ScheduledTask) -> None:
        paths.systemd_user_dir().mkdir(parents=True, exist_ok=True)
        svc = _service_path(task.id)
        tmr = _timer_path(task.id)
        cmd_str = " ".join(task.command)
        svc.write_text(
            f"[Unit]\nDescription={task.description}\n\n"
            f"[Service]\nType=oneshot\nExecStart={cmd_str}\n",
            encoding="utf-8",
        )
        tmr.write_text(
            f"[Unit]\nDescription=Timer for {task.id}\n\n"
            f"[Timer]\nOnCalendar={cron_to_oncalendar(task.cron)}\n"
            f"Persistent=true\n\n"
            f"[Install]\nWantedBy=timers.target\n",
            encoding="utf-8",
        )
        _systemctl("daemon-reload")
        _systemctl("enable", "--now", f"{PREFIX}{task.id}.timer")

    def uninstall(self, task_id: str) -> None:
        unit = f"{PREFIX}{task_id}.timer"
        _systemctl("disable", "--now", unit)
        _systemctl("stop", unit)
        for p in (_service_path(task_id), _timer_path(task_id)):
            if p.exists():
                p.unlink()
        _systemctl("daemon-reload")

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        unit = f"{PREFIX}{task_id}.timer"
        if enabled:
            _systemctl("enable", "--now", unit)
        else:
            _systemctl("disable", "--now", unit)

    def list_native(self) -> list[str]:
        d = paths.systemd_user_dir()
        if not d.exists():
            return []
        out: list[str] = []
        for f in d.glob(f"{PREFIX}*.timer"):
            out.append(f.stem[len(PREFIX) :])
        return out

    def run_once(self, task: ScheduledTask) -> int:
        r = subprocess.run(list(task.command))
        return r.returncode
