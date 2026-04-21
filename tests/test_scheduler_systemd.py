"""Tests for Linux systemd backend."""
import subprocess

from cfo.schemas.schedule import ScheduledTask
from cfo.scheduler.systemd import SystemdBackend, cron_to_oncalendar
from cfo.util import paths


def test_cron_to_oncalendar_weekday_9_15():
    # 15 9 * * 1-5 → Mon..Fri 09:15:00
    out = cron_to_oncalendar("15 9 * * 1-5")
    assert "Mon,Tue,Wed,Thu,Fri" in out or "Mon..Fri" in out
    assert "09:15" in out


def test_cron_to_oncalendar_daily():
    out = cron_to_oncalendar("0 10 * * *")
    assert "10:00" in out


def test_install_creates_service_and_timer(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "systemd_user_dir", lambda: tmp_path)
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
    SystemdBackend().install(t)

    assert (tmp_path / "cfo-daily-prelog.service").exists()
    assert (tmp_path / "cfo-daily-prelog.timer").exists()
    svc = (tmp_path / "cfo-daily-prelog.service").read_text()
    assert "ExecStart=cfo price-log snap" in svc
    # systemctl calls
    assert any(c[0] == "systemctl" for c in calls)


def test_list_native(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "systemd_user_dir", lambda: tmp_path)
    (tmp_path / "cfo-a.timer").write_text("")
    (tmp_path / "cfo-b.timer").write_text("")
    (tmp_path / "other.timer").write_text("")
    ids = sorted(SystemdBackend().list_native())
    assert ids == ["a", "b"]


def test_list_native_missing_dir(tmp_path, monkeypatch):
    missing = tmp_path / "nope"
    monkeypatch.setattr(paths, "systemd_user_dir", lambda: missing)
    assert SystemdBackend().list_native() == []


def test_uninstall_removes_files_and_disables(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "systemd_user_dir", lambda: tmp_path)
    svc = tmp_path / "cfo-x.service"
    tmr = tmp_path / "cfo-x.timer"
    svc.write_text("")
    tmr.write_text("")
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    SystemdBackend().uninstall("x")
    assert not svc.exists() and not tmr.exists()
    assert any("disable" in c or "stop" in c for cmd in calls for c in cmd)


def test_set_enabled_true_and_false(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "systemd_user_dir", lambda: tmp_path)
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    b = SystemdBackend()
    b.set_enabled("x", True)
    assert any("enable" in cmd for c in calls for cmd in c)
    calls.clear()
    b.set_enabled("x", False)
    assert any("disable" in cmd for c in calls for cmd in c)


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
    rc = SystemdBackend().run_once(t)
    assert rc == 0
    assert calls[0] == ["echo", "hi"]


def test_cron_to_oncalendar_rejects_star_minute():
    import pytest

    with pytest.raises(ValueError):
        cron_to_oncalendar("* 9 * * *")


def test_cron_to_oncalendar_rejects_bad_fields():
    import pytest

    with pytest.raises(ValueError):
        cron_to_oncalendar("0 9 1 * *")
    with pytest.raises(ValueError):
        cron_to_oncalendar("0 9 * *")  # only 4 fields


def test_cron_to_oncalendar_dow_7_normalized():
    # DOW 7 == Sunday == 0
    out = cron_to_oncalendar("0 9 * * 7")
    assert "Sun" in out


def test_cron_to_oncalendar_value_out_of_range():
    import pytest

    with pytest.raises(ValueError):
        cron_to_oncalendar("75 9 * * *")
