"""RH Server config, HTTP client, and schedule conversion helpers."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib import error, request

from pydantic import BaseModel, model_validator

from cfo.schemas.schedule import ScheduledTask
from cfo.util import atomic, paths


class RHServerError(RuntimeError):
    """Raised when RH Server config or requests fail."""


class RHServerConfig(BaseModel):
    schema_version: int = 1
    mode: Literal["local", "remote"] = "local"
    base_url: str | None = None
    api_key: str | None = None

    @model_validator(mode="after")
    def _validate_remote_fields(self):
        if self.mode == "remote":
            if not self.base_url or not self.api_key:
                raise ValueError("remote mode requires base_url and api_key")
        return self


def load_config(require: bool = False) -> RHServerConfig | None:
    payload: dict[str, Any] = {}
    config_path = paths.rh_server_json()
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    if os.environ.get("CFO_RH_SERVER_MODE"):
        payload["mode"] = os.environ["CFO_RH_SERVER_MODE"]
    if os.environ.get("CFO_RH_SERVER_URL"):
        payload["base_url"] = os.environ["CFO_RH_SERVER_URL"]
    if os.environ.get("CFO_RH_SERVER_API_KEY"):
        payload["api_key"] = os.environ["CFO_RH_SERVER_API_KEY"]
    if "mode" not in payload and (payload.get("base_url") or payload.get("api_key")):
        payload["mode"] = "remote"
    if not payload:
        if require:
            raise RHServerError(
                "RH Server not configured. Run `cfo schedule connect --server ... --api-key ...` "
                "or set CFO_RH_SERVER_URL/CFO_RH_SERVER_API_KEY."
            )
        return None
    try:
        return RHServerConfig.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise RHServerError(f"invalid RH Server config: {exc}") from exc


def save_config(base_url: str, api_key: str, mode: Literal["local", "remote"] = "remote") -> RHServerConfig:
    cfg = RHServerConfig(mode=mode, base_url=base_url.rstrip("/"), api_key=api_key)
    atomic.write_json(
        paths.rh_server_json(),
        cfg.model_dump(mode="json", exclude_none=True),
    )
    return cfg


def save_mode(mode: Literal["local", "remote"]) -> RHServerConfig:
    current = load_config(require=False)
    payload: dict[str, Any] = {"schema_version": 1, "mode": mode}
    if current:
        if current.base_url:
            payload["base_url"] = current.base_url
        if current.api_key:
            payload["api_key"] = current.api_key
    try:
        cfg = RHServerConfig.model_validate(payload)
    except Exception as exc:
        raise RHServerError(f"invalid RH Server config for mode {mode}: {exc}") from exc
    atomic.write_json(
        paths.rh_server_json(),
        cfg.model_dump(mode="json", exclude_none=True),
    )
    return cfg


def get_mode() -> Literal["local", "remote"]:
    current = load_config(require=False)
    if current is None:
        return "local"
    return current.mode


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 12:
        return api_key
    return f"{api_key[:12]}..."


class RHServerClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "cfo/0.1",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
                message = parsed.get("error") or parsed.get("message") or raw
            except json.JSONDecodeError:
                message = raw or str(exc)
            raise RHServerError(f"RH Server {exc.code}: {message}") from exc
        except error.URLError as exc:
            raise RHServerError(f"RH Server request failed: {exc.reason}") from exc
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RHServerError(f"RH Server returned invalid JSON: {raw}") from exc

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/v1/me")

    def list_schedules(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v1/schedules")
        schedules = payload.get("schedules")
        if schedules is None:
            return []
        if not isinstance(schedules, list):
            raise RHServerError("RH Server returned invalid schedules payload")
        return schedules

    def upsert_schedule(self, name: str, schedule: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/v1/schedules/{name}", schedule)

    def get_schedule(self, name: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/schedules/{name}")

    def delete_schedule(self, name: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/schedules/{name}")

    def enqueue_schedule(self, name: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/schedules/{name}/run", {})

    def list_schedule_runs(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/v1/schedules/{name}/runs?limit={limit}")
        runs = payload.get("runs")
        if runs is None:
            return []
        if not isinstance(runs, list):
            raise RHServerError("RH Server returned invalid runs payload")
        return runs

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/runs/{run_id}")


def write_schedule_index_markdown(
    schedules: list[dict[str, Any]],
    *,
    destination: Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    destination = destination or paths.remote_schedules_md()
    generated_at = generated_at or datetime.now().astimezone()
    destination.parent.mkdir(parents=True, exist_ok=True)

    active = []
    paused = []
    for item in schedules:
        enabled = bool(item.get("enabled", True))
        if enabled:
            active.append(item)
        else:
            paused.append(item)

    lines = [
        "# Remote Schedules",
        "",
        f"Last sync: {generated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
    ]
    lines.extend(_render_schedule_section("Active", active))
    lines.extend(["", *(_render_schedule_section("Paused", paused))])
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return destination


def refresh_schedule_index(client: RHServerClient) -> tuple[list[dict[str, Any]], Path]:
    schedules = client.list_schedules()
    path = write_schedule_index_markdown(schedules)
    return schedules, path


def _render_schedule_section(title: str, schedules: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not schedules:
        lines.append("- None")
        return lines
    for item in sorted(schedules, key=lambda schedule: str(schedule.get("name") or "")):
        trigger = item.get("trigger") or {}
        job = item.get("job") or {}
        note = str(item.get("note") or "").strip()
        command = _command_summary(job)
        summary = note or command or str(job.get("type") or "unknown")
        lines.extend(
            [
                f"- `{item.get('name') or ''}`",
                f"  - Subject: {_subject_summary(item)}",
                f"  - Type: `{job.get('type') or ''}`",
                f"  - Cron: `{trigger.get('expr') or ''}`",
                f"  - Last run: {_display_time(item.get('last_run_at'))}",
                f"  - Summary: {summary}",
                "",
            ]
        )
    return lines[:-1]


def _command_summary(job: dict[str, Any]) -> str:
    spec = job.get("spec") or {}
    command = spec.get("command")
    if isinstance(command, list):
        tokens = [str(token) for token in command]
        return " ".join(tokens)
    return ""


def _subject_summary(schedule: dict[str, Any]) -> str:
    note = str(schedule.get("note") or "").strip()
    if note:
        return note
    job = schedule.get("job") or {}
    spec = job.get("spec") or {}
    command = spec.get("command")
    if isinstance(command, list):
        tokens = [str(token) for token in command]
        if len(tokens) >= 3 and tokens[0] == "rh" and tokens[1] == "quote":
            return f"{tokens[2]} quote"
        return " ".join(tokens)
    return str(job.get("type") or "unknown")


def _display_time(value: Any) -> str:
    parsed = _parse_optional_datetime(value)
    if parsed is None:
        return "-"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M %Z")


def scheduled_task_to_remote(task: ScheduledTask, *, executor_type: str = "worker", executor_target: str = "cfo") -> dict[str, Any]:
    if not task.command:
        raise RHServerError(f"task {task.id} has empty command")
    command_name = task.command[0]
    if command_name == "cfo":
        job_type = "cfo.command"
    elif command_name == "rh":
        job_type = "rh.command"
    else:
        raise RHServerError(f"task {task.id} must start with cfo or rh, got {command_name!r}")
    return {
        "name": task.id,
        "note": task.description,
        "enabled": task.enabled,
        "timezone": task.timezone,
        "trigger": {
            "type": "cron",
            "expr": task.cron,
        },
        "executor": {
            "type": executor_type,
            "target": executor_target,
        },
        "job": {
            "type": job_type,
            "spec": {
                "task_id": task.id,
                "command": task.command,
            },
        },
    }


def remote_schedule_to_task(schedule: dict[str, Any]) -> ScheduledTask:
    trigger = schedule.get("trigger") or {}
    job = schedule.get("job") or {}
    spec = job.get("spec") or {}
    if trigger.get("type") != "cron":
        raise RHServerError(f"schedule {schedule.get('name', '<unknown>')} is not cron-based")
    if job.get("type") not in {"cfo.command", "rh.command"}:
        raise RHServerError(f"schedule {schedule.get('name', '<unknown>')} is not a supported command job")
    command = spec.get("command")
    if not isinstance(command, list) or not all(isinstance(token, str) for token in command):
        raise RHServerError(f"schedule {schedule.get('name', '<unknown>')} has invalid job.spec.command")
    return ScheduledTask(
        id=str(schedule["name"]),
        enabled=bool(schedule.get("enabled", True)),
        cron=str(trigger["expr"]),
        timezone=str(schedule.get("timezone") or "America/Los_Angeles"),
        command=command,
        description=str(schedule.get("note") or ""),
        created_at=_parse_optional_datetime(schedule.get("created_at")),
        last_run=_parse_optional_datetime(schedule.get("last_run_at")),
    )


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    raise RHServerError(f"invalid datetime payload: {value!r}")
