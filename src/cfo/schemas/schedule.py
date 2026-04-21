"""Schedule task schema v1."""
import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class TaskStatus(str, Enum):
    ok = "ok"
    error = "error"
    never_run = "never_run"


class ScheduledTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    enabled: bool = True
    cron: str
    timezone: str = "America/Los_Angeles"
    command: list[str]
    description: str = ""
    created_at: datetime | None = None
    last_run: datetime | None = None
    last_status: TaskStatus | None = None

    @field_validator("cron")
    @classmethod
    def _validate_cron(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError(f"cron must have 5 fields, got {len(parts)}: {v!r}")
        return v.strip()

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(f"id must be alphanumeric/_/-, got {v!r}")
        return v


class SchedulesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    tasks: list[ScheduledTask] = []
