"""Query + summarize cfo-actions.jsonl."""
import json
from collections import Counter
from datetime import date, datetime

from cfo.util import paths, timerange


def _iter_records() -> list[dict]:
    p = paths.audit_log()
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def query(start: date, end: date) -> list[dict]:
    """Return audit records whose ts date is between start and end inclusive."""
    out: list[dict] = []
    for rec in _iter_records():
        ts = rec.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if timerange.datetime_in_range(dt, start, end):
            out.append(rec)
    return out


def summarize(start: date, end: date) -> dict:
    """Aggregate: total/ok/error counts + per-command counts."""
    recs = query(start, end)
    by_cmd: Counter[str] = Counter()
    ok = err = 0
    for r in recs:
        cmd = r.get("cmd", [])
        # Join the 2nd + 3rd tokens for human-readable key: "portfolio show"
        key = " ".join(cmd[1:3]) if len(cmd) >= 3 else (cmd[1] if len(cmd) > 1 else "")
        if key:
            by_cmd[key] += 1
        if r.get("result") == "ok":
            ok += 1
        elif r.get("result") == "error":
            err += 1
    return {
        "total": len(recs),
        "ok": ok,
        "error": err,
        "by_command": dict(by_cmd),
    }
