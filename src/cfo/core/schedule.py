"""CRUD for cfo schedules SSOT (~/.config/cfo/schedules.json)."""
import json

from cfo.schemas.schedule import ScheduledTask, SchedulesFile
from cfo.util import atomic, paths


def _empty() -> SchedulesFile:
    return SchedulesFile(schema_version=1, tasks=[])


def load() -> SchedulesFile:
    p = paths.schedules_json()
    if not p.exists():
        return _empty()
    return SchedulesFile.model_validate(json.loads(p.read_text(encoding="utf-8")))


def save(f: SchedulesFile) -> None:
    atomic.write_json(
        paths.schedules_json(),
        f.model_dump(mode="json", exclude_none=True),
    )


def get(task_id: str) -> ScheduledTask:
    for t in load().tasks:
        if t.id == task_id:
            return t
    raise KeyError(f"task not found: {task_id}")


def add(task: ScheduledTask) -> None:
    f = load()
    if any(t.id == task.id for t in f.tasks):
        raise ValueError(f"task already exists: {task.id}")
    save(f.model_copy(update={"tasks": f.tasks + [task]}))


def remove(task_id: str) -> None:
    f = load()
    new_tasks = [t for t in f.tasks if t.id != task_id]
    if len(new_tasks) == len(f.tasks):
        raise KeyError(f"task not found: {task_id}")
    save(f.model_copy(update={"tasks": new_tasks}))


def set_enabled(task_id: str, enabled: bool) -> None:
    f = load()
    if not any(t.id == task_id for t in f.tasks):
        raise KeyError(f"task not found: {task_id}")
    new_tasks = [
        t.model_copy(update={"enabled": enabled}) if t.id == task_id else t
        for t in f.tasks
    ]
    save(f.model_copy(update={"tasks": new_tasks}))
