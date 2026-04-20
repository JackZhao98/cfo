"""Audit log writer."""
import os
from datetime import datetime, timezone
from typing import Sequence

from cfo.util import atomic, paths


def record(cmd: Sequence[str], result: str, duration_ms: int) -> None:
    """Append one audit record to cfo-actions.jsonl."""
    rec = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "cmd": list(cmd),
        "result": result,
        "duration_ms": duration_ms,
    }
    atomic.append_jsonl(paths.audit_log(), rec)
