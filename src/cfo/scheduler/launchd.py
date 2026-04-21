"""macOS launchd backend — translate schedule to LaunchAgent plist."""
import os
import plistlib
import subprocess
from pathlib import Path

from cfo.schemas.schedule import ScheduledTask
from cfo.util import paths


LABEL_PREFIX = "com.cfo."


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


def cron_to_launchd_calendar(cron: str) -> list[dict]:
    """Translate cron expression to launchd StartCalendarInterval list.

    Only supports: explicit minute/hour (no *), optional DOW list/range.
    Day-of-month and month are ignored if '*', otherwise raise.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(f"cron must have 5 fields: {cron!r}")
    m, h, dom, mon, dow = parts
    if m == "*":
        raise ValueError("minute='*' (every minute) not supported; use specific value")
    if h == "*":
        raise ValueError("hour='*' not supported; use specific value")
    if dom != "*" or mon != "*":
        raise ValueError("day-of-month and month must be '*'")
    minutes = _parse_field(m, range(0, 60))
    hours = _parse_field(h, range(0, 24))
    dows = _parse_field(dow, range(0, 8))  # cron allows 0-7 (both 0 and 7 = Sunday)

    intervals: list[dict] = []
    for hh in hours:
        for mm in minutes:
            if dows == [-1]:
                intervals.append({"Hour": hh, "Minute": mm})
            else:
                for d in dows:
                    d_norm = 0 if d == 7 else d
                    intervals.append({"Hour": hh, "Minute": mm, "Weekday": d_norm})
    return intervals


def _label(task_id: str) -> str:
    return f"{LABEL_PREFIX}{task_id}"


def _plist_path(task_id: str) -> Path:
    return paths.launch_agents_dir() / f"{_label(task_id)}.plist"


def _launchctl(*args: str) -> int:
    r = subprocess.run(
        ["launchctl", *args], capture_output=True, text=True
    )
    return r.returncode


class LaunchdBackend:
    def install(self, task: ScheduledTask) -> None:
        paths.launch_agents_dir().mkdir(parents=True, exist_ok=True)
        intervals = cron_to_launchd_calendar(task.cron)
        audit_dir = paths.data_dir() / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": _label(task.id),
            "ProgramArguments": list(task.command),
            "StartCalendarInterval": intervals,
            "StandardOutPath": str(audit_dir / f"sched-{task.id}.log"),
            "StandardErrorPath": str(audit_dir / f"sched-{task.id}.err"),
            "RunAtLoad": False,
        }
        p = _plist_path(task.id)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:
            plistlib.dump(payload, f)
        # Try new-style bootstrap first, fall back to load
        uid = os.getuid()
        rc = _launchctl("bootstrap", f"gui/{uid}", str(p))
        if rc != 0:
            _launchctl("load", str(p))

    def uninstall(self, task_id: str) -> None:
        p = _plist_path(task_id)
        uid = os.getuid()
        _launchctl("bootout", f"gui/{uid}/{_label(task_id)}")
        if p.exists():
            _launchctl("unload", str(p))
            p.unlink()

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        p = _plist_path(task_id)
        uid = os.getuid()
        if enabled:
            rc = _launchctl("bootstrap", f"gui/{uid}", str(p))
            if rc != 0:
                _launchctl("load", str(p))
        else:
            _launchctl("bootout", f"gui/{uid}/{_label(task_id)}")
            _launchctl("unload", str(p))

    def list_native(self) -> list[str]:
        d = paths.launch_agents_dir()
        if not d.exists():
            return []
        out: list[str] = []
        for f in d.glob(f"{LABEL_PREFIX}*.plist"):
            out.append(f.stem[len(LABEL_PREFIX):])
        return out

    def run_once(self, task: ScheduledTask) -> int:
        r = subprocess.run(list(task.command), capture_output=False)
        return r.returncode
