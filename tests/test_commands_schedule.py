"""Tests for cfo schedule commands."""
import json

from typer.testing import CliRunner
from cfo.util import yaml_io
from cfo.util import paths

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


def test_schedule_export_yaml_file(tmp_data_dir, monkeypatch, tmp_path):
    _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "daily-close",
            "--cron",
            "10 13 * * 1-5",
            "--cmd",
            "cfo",
            "--cmd",
            "status",
            "--description",
            "close snapshot",
        ],
    )
    out = tmp_path / "sched.yaml"
    r = runner.invoke(app, ["schedule", "export", "--file", str(out), "--format", "yaml"])
    assert r.exit_code == 0, r.stdout
    data = yaml_io.load_yaml(out)
    assert data["schema_version"] == 1
    assert data["tasks"][0]["id"] == "daily-close"


def test_schedule_export_json_stdout(tmp_data_dir, monkeypatch):
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
    r = runner.invoke(app, ["schedule", "export", "--format", "json"])
    assert r.exit_code == 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["schema_version"] == 1
    assert payload["tasks"][0]["id"] == "x"


def test_schedule_import_yaml_installs_tasks(tmp_data_dir, monkeypatch, tmp_path):
    calls = _stub_backend(monkeypatch)
    manifest = {
        "schema_version": 1,
        "tasks": [
            {
                "id": "pre-open",
                "enabled": False,
                "cron": "20 6 * * 1-5",
                "timezone": "America/Los_Angeles",
                "command": ["cfo", "status"],
                "description": "pre open",
            }
        ],
    }
    path = tmp_path / "sched.yaml"
    yaml_io.dump_yaml(path, manifest)
    r = runner.invoke(app, ["schedule", "import", "--file", str(path)])
    assert r.exit_code == 0, r.stdout
    task = core.get("pre-open")
    assert task.enabled is False
    assert ("install", "pre-open") in calls
    assert ("set_enabled", "pre-open", False) in calls


def test_schedule_import_duplicate_without_replace_fails(tmp_data_dir, monkeypatch, tmp_path):
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
    path = tmp_path / "sched.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tasks": [
                    {
                        "id": "x",
                        "enabled": True,
                        "cron": "0 10 * * *",
                        "timezone": "America/Los_Angeles",
                        "command": ["echo", "new"],
                        "description": "new",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    r = runner.invoke(app, ["schedule", "import", "--file", str(path)])
    assert r.exit_code == 1
    assert core.get("x").cron == "0 9 * * *"


def test_schedule_import_replace_swaps_tasks(tmp_data_dir, monkeypatch, tmp_path):
    calls = _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "old-task",
            "--cron",
            "0 9 * * *",
            "--cmd",
            "echo",
            "--description",
            "old",
        ],
    )
    path = tmp_path / "sched.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tasks": [
                    {
                        "id": "new-task",
                        "enabled": True,
                        "cron": "10 13 * * 1-5",
                        "timezone": "America/Los_Angeles",
                        "command": ["cfo", "report", "weekly"],
                        "description": "new",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    r = runner.invoke(app, ["schedule", "import", "--file", str(path), "--replace"])
    assert r.exit_code == 0, r.stdout
    ids = [task.id for task in core.load().tasks]
    assert ids == ["new-task"]
    assert ("uninstall", "old-task") in calls
    assert ("install", "new-task") in calls


def test_schedule_remote_set_and_show(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    r = runner.invoke(
        app,
        [
            "schedule",
            "remote-set",
            "--server",
            "https://rh.sentiosurge.com",
            "--api-key",
            "rhs_live_test_123456",
        ],
    )
    assert r.exit_code == 0, r.stdout
    payload = json.loads(paths.rh_server_json().read_text(encoding="utf-8"))
    assert payload["mode"] == "remote"
    assert payload["base_url"] == "https://rh.sentiosurge.com"
    assert payload["api_key"] == "rhs_live_test_123456"

    r2 = runner.invoke(app, ["schedule", "remote-show"])
    assert r2.exit_code == 0, r2.stdout
    assert "remote" in r2.stdout
    assert "https://rh.sentiosurge.com" in r2.stdout
    assert "rhs_live_tes" in r2.stdout


def test_schedule_connect_mode_disconnect(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    r = runner.invoke(
        app,
        [
            "schedule",
            "connect",
            "--server",
            "https://rh.sentiosurge.com",
            "--api-key",
            "rhs_live_test_abcdef",
        ],
    )
    assert r.exit_code == 0, r.stdout
    payload = json.loads(paths.rh_server_json().read_text(encoding="utf-8"))
    assert payload["mode"] == "remote"

    r2 = runner.invoke(app, ["schedule", "mode"])
    assert r2.exit_code == 0
    assert "remote" in r2.stdout

    r3 = runner.invoke(app, ["schedule", "disconnect"])
    assert r3.exit_code == 0, r3.stdout
    payload2 = json.loads(paths.rh_server_json().read_text(encoding="utf-8"))
    assert payload2["mode"] == "local"
    assert payload2["base_url"] == "https://rh.sentiosurge.com"


def test_schedule_remote_mode_add_list_pause_resume_remove_run(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    monkeypatch.setattr("cfo.commands.schedule._mode", lambda: "remote")

    state = {
        "daily-close": {
            "name": "daily-close",
            "note": "close snapshot",
            "enabled": True,
            "timezone": "America/Los_Angeles",
            "trigger": {"type": "cron", "expr": "10 13 * * 1-5"},
            "executor": {"type": "worker", "target": "cfo"},
            "job": {"type": "cfo.command", "spec": {"command": ["cfo", "status"]}},
        }
    }
    enqueued: list[str] = []

    class StubClient:
        def upsert_schedule(self, name, schedule):
            state[name] = schedule
            return schedule

        def list_schedules(self):
            return list(state.values())

        def get_schedule(self, name):
            if name not in state:
                raise RuntimeError("missing")
            return dict(state[name])

        def delete_schedule(self, name):
            state.pop(name)
            return {"deleted": name}

        def enqueue_schedule(self, name):
            enqueued.append(name)
            return {"id": "run-123"}

    monkeypatch.setattr("cfo.commands.schedule._remote_client", lambda: StubClient())

    r_add = runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "pre-open",
            "--cron",
            "20 6 * * 1-5",
            "--cmd",
            "cfo",
            "--cmd",
            "price-log",
            "--description",
            "pre open",
        ],
    )
    assert r_add.exit_code == 0, r_add.stdout
    assert "pre-open" in state
    index_text = paths.remote_schedules_md().read_text(encoding="utf-8")
    assert "# Remote Schedules" in index_text
    assert "`pre-open`" in index_text

    r_list = runner.invoke(app, ["schedule", "list"])
    assert r_list.exit_code == 0, r_list.stdout
    assert "pre-open" in r_list.stdout

    r_pause = runner.invoke(app, ["schedule", "pause", "daily-close"])
    assert r_pause.exit_code == 0, r_pause.stdout
    assert state["daily-close"]["enabled"] is False
    paused_index = paths.remote_schedules_md().read_text(encoding="utf-8")
    assert "## Paused" in paused_index
    assert "`daily-close`" in paused_index

    r_resume = runner.invoke(app, ["schedule", "resume", "daily-close"])
    assert r_resume.exit_code == 0, r_resume.stdout
    assert state["daily-close"]["enabled"] is True

    r_run = runner.invoke(app, ["schedule", "run", "daily-close"])
    assert r_run.exit_code == 0, r_run.stdout
    assert enqueued == ["daily-close"]

    r_remove = runner.invoke(app, ["schedule", "remove", "daily-close"])
    assert r_remove.exit_code == 0, r_remove.stdout
    assert "daily-close" not in state


def test_schedule_push_uses_remote_client(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "daily-close",
            "--cron",
            "10 13 * * 1-5",
            "--cmd",
            "cfo",
            "--cmd",
            "status",
            "--description",
            "close snapshot",
        ],
    )

    pushed: list[tuple[str, dict]] = []

    class StubClient:
        def upsert_schedule(self, name, schedule):
            pushed.append((name, schedule))
            return schedule

        def list_schedules(self):
            return [item[1] for item in pushed]

    monkeypatch.setattr("cfo.commands.schedule._remote_client", lambda: StubClient())
    r = runner.invoke(
        app,
        [
            "schedule",
            "push",
            "--executor-target",
            "cfo-macbook",
        ],
    )
    assert r.exit_code == 0, r.stdout
    assert len(pushed) == 1
    name, payload = pushed[0]
    assert name == "daily-close"
    assert payload["job"]["type"] == "cfo.command"
    assert payload["job"]["spec"]["command"] == ["cfo", "status"]
    assert payload["executor"]["target"] == "cfo-macbook"


def test_schedule_push_uses_rh_command_for_rh_tasks(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    runner.invoke(
        app,
        [
            "schedule",
            "add",
            "--id",
            "quote-qqq",
            "--cron",
            "0 9 * * 1-5",
            "--cmd",
            "rh",
            "--cmd",
            "quote",
            "--cmd",
            "QQQ",
            "--description",
            "quote snapshot",
        ],
    )

    pushed: list[tuple[str, dict]] = []

    class StubClient:
        def upsert_schedule(self, name, schedule):
            pushed.append((name, schedule))
            return schedule

        def list_schedules(self):
            return [item[1] for item in pushed]

    monkeypatch.setattr("cfo.commands.schedule._remote_client", lambda: StubClient())
    r = runner.invoke(app, ["schedule", "push", "--id", "quote-qqq"])
    assert r.exit_code == 0, r.stdout
    _, payload = pushed[0]
    assert payload["job"]["type"] == "rh.command"
    assert payload["job"]["spec"]["command"] == ["rh", "quote", "QQQ"]


def test_schedule_pull_imports_only_cfo_command(tmp_data_dir, monkeypatch):
    calls = _stub_backend(monkeypatch)

    class StubClient:
        def list_schedules(self):
            return [
                {
                    "name": "daily-close",
                    "note": "close snapshot",
                    "enabled": True,
                    "timezone": "America/Los_Angeles",
                    "trigger": {"type": "cron", "expr": "10 13 * * 1-5"},
                    "executor": {"type": "worker", "target": "cfo"},
                    "job": {"type": "cfo.command", "spec": {"command": ["cfo", "status"]}},
                    "created_at": "2026-04-21T20:00:00Z",
                },
                {
                    "name": "non-cfo-job",
                    "note": "skip me",
                    "enabled": True,
                    "timezone": "America/Los_Angeles",
                    "trigger": {"type": "cron", "expr": "0 9 * * *"},
                    "executor": {"type": "server"},
                    "job": {"type": "rh.quote_capture", "spec": {"symbol": "QQQ"}},
                    "created_at": "2026-04-21T20:00:00Z",
                },
                {
                    "name": "quote-qqq",
                    "note": "quote snapshot",
                    "enabled": True,
                    "timezone": "America/Los_Angeles",
                    "trigger": {"type": "cron", "expr": "0 9 * * 1-5"},
                    "executor": {"type": "worker", "target": "cfo"},
                    "job": {"type": "rh.command", "spec": {"command": ["rh", "quote", "QQQ"]}},
                    "created_at": "2026-04-21T20:00:00Z",
                },
            ]

    monkeypatch.setattr("cfo.commands.schedule._remote_client", lambda: StubClient())
    r = runner.invoke(app, ["schedule", "pull", "--install"])
    assert r.exit_code == 0, r.stdout
    task = core.get("daily-close")
    assert task.command == ["cfo", "status"]
    assert task.description == "close snapshot"
    rh_task = core.get("quote-qqq")
    assert rh_task.command == ["rh", "quote", "QQQ"]
    assert ("install", "daily-close") in calls
    assert ("install", "quote-qqq") in calls
    assert "non-CFO remote schedule" in r.stdout


def test_schedule_runs_and_run_show_remote_mode(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    monkeypatch.setattr("cfo.commands.schedule._mode", lambda: "remote")

    class StubClient:
        def list_schedule_runs(self, name, limit=20):
            assert name == "quote-qqq"
            assert limit == 5
            return [
                {
                    "id": "run-1",
                    "created_at": "2026-04-21T20:00:00Z",
                    "status": "succeeded",
                    "worker_name": "server-worker",
                    "job_type": "rh.command",
                }
            ]

        def get_run(self, run_id):
            assert run_id == "run-1"
            return {
                "run": {
                    "id": "run-1",
                    "schedule_name": "quote-qqq",
                    "status": "succeeded",
                    "created_at": "2026-04-21T20:00:00Z",
                    "worker_name": "server-worker",
                },
                "artifacts": {
                    "paths": {"result_path": "/tmp/result.json"},
                    "result": {"kind": "json", "payload": {"symbol": "QQQ"}},
                },
            }

    monkeypatch.setattr("cfo.commands.schedule._remote_client", lambda: StubClient())

    r1 = runner.invoke(app, ["schedule", "runs", "quote-qqq", "--limit", "5"])
    assert r1.exit_code == 0, r1.stdout
    assert "run-1" in r1.stdout
    assert "succeeded" in r1.stdout

    r2 = runner.invoke(app, ["schedule", "run-show", "run-1"])
    assert r2.exit_code == 0, r2.stdout
    assert "quote-qqq" in r2.stdout
    assert '"symbol": "QQQ"' in r2.stdout


def test_schedule_refresh_writes_remote_index(tmp_data_dir, monkeypatch):
    _stub_backend(monkeypatch)
    monkeypatch.setattr("cfo.commands.schedule._mode", lambda: "remote")

    class StubClient:
        def list_schedules(self):
            return [
                {
                    "name": "tsla-quote-5m",
                    "note": "Track TSLA quote every 5 minutes",
                    "enabled": True,
                    "timezone": "America/Los_Angeles",
                    "trigger": {"type": "cron", "expr": "*/5 * * * *"},
                    "executor": {"type": "worker", "target": "cfo"},
                    "job": {"type": "rh.command", "spec": {"command": ["rh", "quote", "TSLA", "--format", "json"]}},
                    "last_run_at": "2026-04-21T20:46:17Z",
                },
                {
                    "name": "qqq-option-5m",
                    "note": "Track QQQ option chain",
                    "enabled": False,
                    "timezone": "America/Los_Angeles",
                    "trigger": {"type": "cron", "expr": "*/5 * * * *"},
                    "executor": {"type": "worker", "target": "cfo"},
                    "job": {"type": "rh.command", "spec": {"command": ["rh", "option", "chain", "QQQ"]}},
                    "last_run_at": "2026-04-21T20:40:00Z",
                },
            ]

    monkeypatch.setattr("cfo.commands.schedule._remote_client", lambda: StubClient())

    r = runner.invoke(app, ["schedule", "refresh"])
    assert r.exit_code == 0, r.stdout
    text = paths.remote_schedules_md().read_text(encoding="utf-8")
    assert "# Remote Schedules" in text
    assert "## Active" in text
    assert "## Paused" in text
    assert "`tsla-quote-5m`" in text
    assert "`qqq-option-5m`" in text
    assert "Track TSLA quote every 5 minutes" in text
