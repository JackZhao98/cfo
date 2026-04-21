"""Tests for macOS launchd scheduler backend."""
import plistlib
import subprocess

import pytest

from cfo.schemas.schedule import ScheduledTask
from cfo.scheduler.launchd import LaunchdBackend, cron_to_launchd_calendar
from cfo.util import paths


def test_cron_every_weekday_at_9_15():
    # 15 9 * * 1-5
    intervals = cron_to_launchd_calendar("15 9 * * 1-5")
    # Expect a list covering 1..5 for DayOfWeek at Hour=9 Minute=15
    assert len(intervals) == 5
    dows = sorted(i["Weekday"] for i in intervals)
    assert dows == [1, 2, 3, 4, 5]
    assert all(i["Hour"] == 9 and i["Minute"] == 15 for i in intervals)


def test_cron_every_day_at_10():
    # 0 10 * * *
    intervals = cron_to_launchd_calendar("0 10 * * *")
    # No DOW restriction — single dict
    assert intervals == [{"Hour": 10, "Minute": 0}]


def test_cron_unsupported_minute_star_raises():
    # Minute=* means every minute, not supported without StartInterval
    with pytest.raises(ValueError):
        cron_to_launchd_calendar("* 9 * * 1-5")


def test_cron_unsupported_hour_star_raises():
    with pytest.raises(ValueError):
        cron_to_launchd_calendar("0 * * * *")


def test_cron_unsupported_day_of_month_raises():
    with pytest.raises(ValueError):
        cron_to_launchd_calendar("0 9 1 * *")


def test_cron_unsupported_month_raises():
    with pytest.raises(ValueError):
        cron_to_launchd_calendar("0 9 * 1 *")


def test_cron_wrong_field_count_raises():
    with pytest.raises(ValueError):
        cron_to_launchd_calendar("0 9 * *")


def test_cron_out_of_range_minute_raises():
    with pytest.raises(ValueError):
        cron_to_launchd_calendar("60 9 * * *")


def test_cron_dow_list():
    # 0 10 * * 1,3,5
    intervals = cron_to_launchd_calendar("0 10 * * 1,3,5")
    assert len(intervals) == 3
    dows = sorted(i["Weekday"] for i in intervals)
    assert dows == [1, 3, 5]


def test_cron_dow_sunday_7_normalized_to_0():
    # cron allows 7 as Sunday — launchd uses 0
    intervals = cron_to_launchd_calendar("0 10 * * 7")
    assert intervals == [{"Hour": 10, "Minute": 0, "Weekday": 0}]


def test_cron_multiple_minutes_and_hours():
    # 0,30 9,10 * * *  -> 4 intervals
    intervals = cron_to_launchd_calendar("0,30 9,10 * * *")
    assert len(intervals) == 4


def test_install_writes_plist(tmp_path, monkeypatch, tmp_data_dir):
    # Redirect LaunchAgents dir
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: tmp_path)

    # Stub launchctl
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    t = ScheduledTask(
        id="daily-prelog",
        cron="15 9 * * 1-5",
        command=["cfo", "price-log", "snap"],
        description="test",
    )
    LaunchdBackend().install(t)

    plist = tmp_path / "com.cfo.daily-prelog.plist"
    assert plist.exists()
    with plist.open("rb") as f:
        data = plistlib.load(f)
    assert data["Label"] == "com.cfo.daily-prelog"
    assert data["ProgramArguments"] == ["cfo", "price-log", "snap"]
    assert len(data["StartCalendarInterval"]) == 5
    # launchctl was invoked
    assert any(c[0] == "launchctl" for c in calls)


def test_install_falls_back_to_load_when_bootstrap_fails(tmp_path, monkeypatch, tmp_data_dir):
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: tmp_path)
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            # bootstrap fails, load succeeds
            returncode = 1 if "bootstrap" in cmd else 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    t = ScheduledTask(
        id="fallback",
        cron="0 9 * * *",
        command=["echo", "hi"],
        description="test",
    )
    LaunchdBackend().install(t)
    # Should have attempted both bootstrap and load
    assert any("bootstrap" in c for c in calls)
    assert any("load" in c for c in calls)


def test_uninstall_removes_plist_and_unloads(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: tmp_path)
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Create fake plist
    plist = tmp_path / "com.cfo.daily-prelog.plist"
    plist.write_text("<plist/>")

    LaunchdBackend().uninstall("daily-prelog")
    assert not plist.exists()
    assert any(c[0] == "launchctl" for c in calls)


def test_uninstall_missing_plist_still_calls_bootout(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: tmp_path)
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    LaunchdBackend().uninstall("nonexistent")
    # bootout still attempted
    assert any("bootout" in c for c in calls)


def test_list_native(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: tmp_path)
    (tmp_path / "com.cfo.a.plist").write_text("<plist/>")
    (tmp_path / "com.cfo.b.plist").write_text("<plist/>")
    (tmp_path / "com.other.c.plist").write_text("<plist/>")
    ids = sorted(LaunchdBackend().list_native())
    assert ids == ["a", "b"]


def test_list_native_missing_dir(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: missing)
    assert LaunchdBackend().list_native() == []


def test_set_enabled_unloads_on_false(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: tmp_path)
    (tmp_path / "com.cfo.x.plist").write_text("<plist/>")
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    LaunchdBackend().set_enabled("x", False)
    # Should call launchctl unload (or bootout)
    assert any(
        "launchctl" in c[0] and ("unload" in c[1] or "bootout" in c[1]) for c in calls
    )


def test_set_enabled_loads_on_true(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "launch_agents_dir", lambda: tmp_path)
    (tmp_path / "com.cfo.x.plist").write_text("<plist/>")
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    LaunchdBackend().set_enabled("x", True)
    assert any(
        "launchctl" in c[0] and ("bootstrap" in c[1] or "load" in c[1]) for c in calls
    )


def test_run_once_executes(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    t = ScheduledTask(
        id="x", cron="0 0 * * *", command=["echo", "hi"], description="x"
    )
    rc = LaunchdBackend().run_once(t)
    assert rc == 0
    assert calls[0] == ["echo", "hi"]


def test_run_once_propagates_nonzero(tmp_path, monkeypatch):
    def fake_run(cmd, *a, **k):
        class R:
            returncode = 42
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    t = ScheduledTask(id="x", cron="0 0 * * *", command=["false"], description="x")
    rc = LaunchdBackend().run_once(t)
    assert rc == 42
