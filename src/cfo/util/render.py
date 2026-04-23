"""Shared output rendering helpers for human and AI-friendly CLI output."""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from rich.console import Console


class OutputFormat(str, Enum):
    table = "table"
    plain = "plain"
    json = "json"


def format_local_dt(value: datetime | None, *, timespec: str = "minutes") -> str:
    if value is None:
        return "-"
    return value.astimezone().isoformat(timespec=timespec)


def to_serializable(value: Any, *, local_time: bool = False) -> Any:
    if isinstance(value, BaseModel):
        return to_serializable(value.model_dump(mode="python", exclude_none=True), local_time=local_time)
    if isinstance(value, dict):
        return {str(k): to_serializable(v, local_time=local_time) for k, v in value.items()}
    if isinstance(value, list):
        return [to_serializable(v, local_time=local_time) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if local_time:
            return value.astimezone().isoformat(timespec="seconds")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def render_json(console: Console, data: Any) -> None:
    console.print(json.dumps(to_serializable(data, local_time=False), ensure_ascii=False, indent=2), markup=False)


def render_plain(console: Console, data: Any) -> None:
    lines = _render_plain_lines(to_serializable(data, local_time=True))
    console.print("\n".join(lines), markup=False)


def _render_plain_lines(data: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent

    if isinstance(data, dict):
        if not data:
            return [prefix + "{}"]
        lines: list[str] = []
        for key, value in data.items():
            if _is_scalar(value):
                lines.append(f"{prefix}{key}: {_scalar_text(value)}")
            else:
                lines.append(f"{prefix}{key}:")
                lines.extend(_render_plain_lines(value, indent + 1))
        return lines

    if isinstance(data, list):
        if not data:
            return [prefix + "[]"]
        lines = []
        for value in data:
            if _is_scalar(value):
                lines.append(f"{prefix}- {_scalar_text(value)}")
            else:
                lines.append(f"{prefix}-")
                lines.extend(_render_plain_lines(value, indent + 1))
        return lines

    return [prefix + _scalar_text(data)]


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (dict, list))


def _scalar_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
