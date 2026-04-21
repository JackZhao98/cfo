"""Tests for cfo schedule commands."""
from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import schedule as core

runner = CliRunner()


def _stub_backend(monkeypatch):
    """Replace the real backend with a no-op that records calls."""
    calls: list[tuple] = []

    class StubBackend:
        def install(self, task):
            calls.append(("install", task.id))

        def uninstall(self, task_id):
            calls.append(("uninstall", task_id))

        def set_enabled(self, task_id, enabled):
            calls.append(("set_enabled", task_id, enabled))

        def list_native(self):
            return []

        def run_once(self, task):
            calls.append(("run_once", task.id))
            return 0

    from cfo.scheduler import registry

    monkeypatch.setattr(registry, "get_backend", lambda: StubBackend())
    return calls


def test_schedule_add(tmp_data_dir, monkeypatch):
    calls = _stub_backend(monkeypatch)
    r = runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "daily-prelog",
            "--cron",
            "15 9 * * 1-5",
            "--cmd",
            "cfo",
            "--cmd",
            "price-log",
            "--cmd",
            "snap",
            "--description",
            "Pre-market",
        ],
    )
    assert r.exit_code == 0, r.stdout
    f = core.load()
    assert len(f.tasks) == 1
    assert f.tasks[0].id == "daily-prelog"
    assert any(c[0] == "install" for c in calls)


def test_schedule_add_duplicate_fails(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "x",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--description",
            "x",
        ],
    )
    r = runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "x",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--description",
            "x",
        ],
    )
    assert r.exit_code == 1


def test_schedule_list_empty(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    r = runner.invoke(app, ["schedule", "list"])
    assert r.exit_code == 0
    assert "no scheduled tasks" in r.stdout.lower()


def test_schedule_list_with_tasks(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "a",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--cmd",
            "hi",
            "--description",
            "x",
        ],
    )
    r = runner.invoke(app, ["schedule", "list"])
    assert r.exit_code == 0
    assert "a" in r.stdout


def test_schedule_pause_and_resume(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "x",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--description",
            "x",
        ],
    )
    r = runner.invoke(app, ["schedule", "pause", "x"])
    assert r.exit_code == 0
    assert core.get("x").enabled is False
    r2 = runner.invoke(app, ["schedule", "resume", "x"])
    assert r2.exit_code == 0
    assert core.get("x").enabled is True


def test_schedule_pause_missing(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    r = runner.invoke(app, ["schedule", "pause", "nonexistent"])
    assert r.exit_code == 1


def test_schedule_resume_missing(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    r = runner.invoke(app, ["schedule", "resume", "nonexistent"])
    assert r.exit_code == 1


def test_schedule_remove(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "x",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--description",
            "x",
        ],
    )
    r = runner.invoke(app, ["schedule", "remove", "x"])
    assert r.exit_code == 0
    assert core.load().tasks == []


def test_schedule_remove_missing(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    r = runner.invoke(app, ["schedule", "remove", "nonexistent"])
    assert r.exit_code == 1


def test_schedule_run(tmp_data_dir, monkeypatch):
    calls = _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "x",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--description",
            "x",
        ],
    )
    r = runner.invoke(app, ["schedule", "run", "x"])
    assert r.exit_code == 0
    assert any(c[0] == "run_once" for c in calls)


def test_schedule_run_missing(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    r = runner.invoke(app, ["schedule", "run", "nonexistent"])
    assert r.exit_code == 1


def test_schedule_run_nonzero_exit(tmp_data_dir, monkeypatch):
    calls: list[tuple] = []

    class StubBackend:
        def install(self, task):
            calls.append(("install", task.id))

        def uninstall(self, task_id):
            pass

        def set_enabled(self, task_id, enabled):
            pass

        def list_native(self):
            return []

        def run_once(self, task):
            return 2

    from cfo.scheduler import registry

    monkeypatch.setattr(registry, "get_backend", lambda: StubBackend())
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "x",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "false",
            "--description",
            "x",
        ],
    )
    r = runner.invoke(app, ["schedule", "run", "x"])
    assert r.exit_code == 2


def test_schedule_add_backend_install_failure_rolls_back(tmp_data_dir, monkeypatch):
    class StubBackend:
        def install(self, task):
            raise RuntimeError("boom")

        def uninstall(self, task_id):
            pass

        def set_enabled(self, task_id, enabled):
            pass

        def list_native(self):
            return []

        def run_once(self, task):
            return 0

    from cfo.scheduler import registry

    monkeypatch.setattr(registry, "get_backend", lambda: StubBackend())
    r = runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "x",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--description",
            "x",
        ],
    )
    assert r.exit_code == 1
    # State rolled back
    assert core.load().tasks == []
