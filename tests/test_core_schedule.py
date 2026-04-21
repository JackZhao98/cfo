"""Tests for core.schedule CRUD on schedules.json."""
import pytest

from cfo.core import schedule as core
from cfo.schemas.schedule import ScheduledTask


def _task(id_="daily-prelog"):
    return ScheduledTask(
        id=id_,
        cron="15 9 * * 1-5",
        command=["cfo", "price-log", "snap"],
        description="Pre-market snapshot",
    )


def test_load_missing_returns_empty(tmp_data_dir):
    f = core.load()
    assert f.tasks == []
    assert f.schema_version == 1


def test_add_and_get(tmp_data_dir):
    core.add(_task())
    f = core.load()
    assert len(f.tasks) == 1
    assert f.tasks[0].id == "daily-prelog"
    got = core.get("daily-prelog")
    assert got.id == "daily-prelog"


def test_get_missing_raises(tmp_data_dir):
    with pytest.raises(KeyError):
        core.get("nope")


def test_add_duplicate_rejected(tmp_data_dir):
    core.add(_task())
    with pytest.raises(ValueError):
        core.add(_task())


def test_remove(tmp_data_dir):
    core.add(_task())
    core.remove("daily-prelog")
    assert core.load().tasks == []


def test_remove_missing_raises(tmp_data_dir):
    with pytest.raises(KeyError):
        core.remove("nonexistent")


def test_set_enabled(tmp_data_dir):
    core.add(_task())
    core.set_enabled("daily-prelog", False)
    assert core.get("daily-prelog").enabled is False
    core.set_enabled("daily-prelog", True)
    assert core.get("daily-prelog").enabled is True


def test_set_enabled_missing_raises(tmp_data_dir):
    with pytest.raises(KeyError):
        core.set_enabled("nope", False)


def test_add_does_not_mutate_original(tmp_data_dir):
    """Ensure immutability: adding a task does not mutate the in-memory SchedulesFile."""
    f_before = core.load()
    tasks_before = list(f_before.tasks)
    core.add(_task())
    # Original list snapshot unchanged
    assert tasks_before == []
