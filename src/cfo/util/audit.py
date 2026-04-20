"""Audit log writer."""
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Literal

from cfo.util import atomic, paths


def record(cmd: Sequence[str], result: Literal["ok", "error"], duration_ms: int) -> None:
    """Append one audit record to cfo-actions.jsonl."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "cmd": list(cmd),
        "result": result,
        "duration_ms": duration_ms,
    }
    atomic.append_jsonl(paths.audit_log(), rec)
