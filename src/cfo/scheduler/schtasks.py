"""Windows schtasks backend."""
import csv
import io
import subprocess

from cfo.schemas.schedule import ScheduledTask


PREFIX = "cfo-"

_DOW_NAMES = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]


def _parse_field(field: str, valid_range: range) -> list[int]:
    if field == "*":
        return [-1]
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


def cron_to_schtasks_args(cron: str) -> list[str]:
    """Translate cron → schtasks scheduling args.

    Supports: DAILY (dow='*') or WEEKLY (dow list/range), single minute/hour.
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
    dows = _parse_field(dow, range(0, 8))
    if len(minutes) != 1 or len(hours) != 1:
        raise ValueError("schtasks backend only supports single minute/hour")
    st = f"{hours[0]:02d}:{minutes[0]:02d}"

    if dows == [-1]:
        return ["/SC", "DAILY", "/ST", st]
    norm = sorted({0 if d == 7 else d for d in dows})
    day_arg = ",".join(_DOW_NAMES[d] for d in norm)
    return ["/SC", "WEEKLY", "/D", day_arg, "/ST", st]


def _task_name(task_id: str) -> str:
    return f"{PREFIX}{task_id}"


class SchtasksBackend:
    def install(self, task: ScheduledTask) -> None:
        tn = _task_name(task.id)
        if hasattr(subprocess, "list2cmdline"):
            tr = subprocess.list2cmdline(list(task.command))
        else:
            tr = " ".join(task.command)
        args = [
            "schtasks",
            "/Create",
            "/TN",
            tn,
            "/TR",
            tr,
            "/F",
            *cron_to_schtasks_args(task.cron),
        ]
        subprocess.run(args, capture_output=True, text=True)

    def uninstall(self, task_id: str) -> None:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", _task_name(task_id), "/F"],
            capture_output=True,
            text=True,
        )

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        flag = "/ENABLE" if enabled else "/DISABLE"
        subprocess.run(
            ["schtasks", "/Change", "/TN", _task_name(task_id), flag],
            capture_output=True,
            text=True,
        )

    def list_native(self) -> list[str]:
        r = subprocess.run(
            ["schtasks", "/Query", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return []
        out: list[str] = []
        reader = csv.reader(io.StringIO(r.stdout))
        for row in reader:
            if not row:
                continue
            name = row[0].strip().lstrip("\\")
            if name.startswith(PREFIX):
                out.append(name[len(PREFIX) :])
        return out

    def run_once(self, task: ScheduledTask) -> int:
        r = subprocess.run(list(task.command))
        return r.returncode
