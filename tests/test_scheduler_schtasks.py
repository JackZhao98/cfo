"""Tests for Windows schtasks backend."""
import subprocess

import pytest

from cfo.schemas.schedule import ScheduledTask
from cfo.scheduler.schtasks import SchtasksBackend, cron_to_schtasks_args


def test_cron_args_weekday_9_15():
    args = cron_to_schtasks_args("15 9 * * 1-5")
    # Expect WEEKLY with /D MON,TUE,WED,THU,FRI /ST 09:15
    joined = " ".join(args)
    assert "WEEKLY" in joined
    assert "MON" in joined and "FRI" in joined
    assert "09:15" in joined


def test_cron_args_daily():
    args = cron_to_schtasks_args("0 10 * * *")
    joined = " ".join(args)
    assert "DAILY" in joined
    assert "10:00" in joined


def test_cron_args_rejects_star_minute():
    with pytest.raises(ValueError):
        cron_to_schtasks_args("* 9 * * *")


def test_cron_args_rejects_bad_length():
    with pytest.raises(ValueError):
        cron_to_schtasks_args("0 9 * *")


def test_cron_args_rejects_dom_or_mon():
    with pytest.raises(ValueError):
        cron_to_schtasks_args("0 9 1 * *")


def test_cron_args_rejects_multiple_times():
    with pytest.raises(ValueError):
        cron_to_schtasks_args("0,30 9 * * *")


def test_cron_args_dow_7_normalized_to_sun():
    args = cron_to_schtasks_args("0 9 * * 7")
    assert "SUN" in " ".join(args)


def test_cron_args_value_out_of_range():
    with pytest.raises(ValueError):
        cron_to_schtasks_args("0 25 * * *")


def test_install_calls_schtasks(monkeypatch):
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
        description="x",
    )
    SchtasksBackend().install(t)
    assert calls and calls[0][0] == "schtasks"
    joined = " ".join(calls[0])
    assert "/Create" in joined
    assert "/TN" in joined and "cfo-daily-prelog" in joined


def test_uninstall_calls_delete(monkeypatch):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    SchtasksBackend().uninstall("x")
    assert calls[0][0] == "schtasks" and "/Delete" in calls[0]


def test_set_enabled_true(monkeypatch):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    SchtasksBackend().set_enabled("x", True)
    assert calls[0][0] == "schtasks"
    assert "/Change" in calls[0]
    assert "/ENABLE" in calls[0]


def test_set_enabled_false(monkeypatch):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    SchtasksBackend().set_enabled("x", False)
    assert "/DISABLE" in calls[0]


def test_list_native(monkeypatch):
    # schtasks /Query /FO CSV output
    csv_txt = (
        '"TaskName","Next Run Time","Status"\n'
        '"\\cfo-a","2026-04-21 09:15:00","Ready"\n'
        '"\\cfo-b","2026-04-22 09:15:00","Ready"\n'
        '"\\other-task","2026-04-22 09:15:00","Ready"\n'
    )

    class R:
        returncode = 0
        stdout = csv_txt
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    ids = sorted(SchtasksBackend().list_native())
    assert ids == ["a", "b"]


def test_list_native_error_returns_empty(monkeypatch):
    class R:
        returncode = 1
        stdout = ""
        stderr = "nope"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert SchtasksBackend().list_native() == []


def test_run_once_executes(monkeypatch):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    t = ScheduledTask(id="x", cron="0 0 * * *", command=["echo", "hi"], description="x")
    rc = SchtasksBackend().run_once(t)
    assert rc == 0
    assert calls[0] == ["echo", "hi"]
