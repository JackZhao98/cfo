"""Tests for schedule schema."""
import pytest
from pydantic import ValidationError

from cfo.schemas.schedule import ScheduledTask, SchedulesFile, TaskStatus


def test_task_minimal():
    t = ScheduledTask(
        id="daily-prelog",
        cron="15 9 * * 1-5",
        command=["cfo", "price-log", "snap", "--watchlist"],
        description="Pre-market snapshot",
    )
    assert t.enabled is True
    assert t.timezone == "America/Los_Angeles"
    assert t.last_status is None


def test_task_rejects_bad_cron():
    with pytest.raises(ValidationError):
        ScheduledTask(id="x", cron="not-a-cron", command=["echo"], description="x")


def test_task_rejects_bad_id():
    with pytest.raises(ValidationError):
        ScheduledTask(id="bad id!", cron="0 9 * * *", command=["echo"], description="x")


def test_schedules_file_roundtrip():
    f = SchedulesFile(
        schema_version=1,
        tasks=[ScheduledTask(id="x", cron="0 9 * * *", command=["echo"], description="x")],
    )
    data = f.model_dump(mode="json", exclude_none=True)
    reloaded = SchedulesFile.model_validate(data)
    assert reloaded.tasks[0].id == "x"


def test_task_status_values():
    assert TaskStatus.ok.value == "ok"
    assert TaskStatus.error.value == "error"
    assert TaskStatus.never_run.value == "never_run"
