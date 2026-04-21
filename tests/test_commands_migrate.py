"""Tests for 'cfo migrate paths'."""
from pathlib import Path

from typer.testing import CliRunner

from cfo.cli import app
from cfo.util import paths

runner = CliRunner()


def _with_legacy(monkeypatch, tmp_data_dir, legacy_data: Path, legacy_config: Path):
    """Redirect paths legacy lists to tmp locations."""
    monkeypatch.setattr(paths, "LEGACY_DATA_DIRS", [legacy_data])
    monkeypatch.setattr(paths, "LEGACY_CONFIG_DIRS", [legacy_config])


def test_migrate_paths_moves_data_and_config(tmp_data_dir, tmp_path, monkeypatch):
    legacy_data = tmp_path / "legacy-data"
    legacy_cfg = tmp_path / "legacy-config"
    legacy_data.mkdir()
    (legacy_data / "portfolio").mkdir()
    (legacy_data / "portfolio" / "profile.md").write_text("# Jack\n")
    legacy_cfg.mkdir()
    (legacy_cfg / "schedules.json").write_text('{"schema_version":1,"tasks":[]}')

    _with_legacy(monkeypatch, tmp_data_dir, legacy_data, legacy_cfg)

    r = runner.invoke(app, ["migrate", "paths"])
    assert r.exit_code == 0, r.stdout

    new_profile = paths.profile_md()
    new_sched = paths.schedules_json()
    assert new_profile.exists()
    assert new_profile.read_text() == "# Jack\n"
    assert new_sched.exists()
    # Legacy dirs should be gone (or empty)
    assert not legacy_data.exists() or not any(legacy_data.iterdir())


def test_migrate_paths_idempotent(tmp_data_dir, tmp_path, monkeypatch):
    legacy_data = tmp_path / "legacy"
    _with_legacy(monkeypatch, tmp_data_dir, legacy_data, tmp_path / "none")
    # Legacy doesn't exist
    r = runner.invoke(app, ["migrate", "paths"])
    assert r.exit_code == 0
    assert "nothing to migrate" in r.stdout.lower()


def test_migrate_paths_dry_run(tmp_data_dir, tmp_path, monkeypatch):
    legacy_data = tmp_path / "legacy-data"
    legacy_data.mkdir()
    (legacy_data / "x.txt").write_text("y")
    _with_legacy(monkeypatch, tmp_data_dir, legacy_data, tmp_path / "none")
    r = runner.invoke(app, ["migrate", "paths", "--dry-run"])
    assert r.exit_code == 0
    assert "would move" in r.stdout.lower()
    # Nothing actually moved
    assert legacy_data.exists()
    assert (legacy_data / "x.txt").exists()


def test_migrate_paths_merges_without_overwriting(tmp_data_dir, tmp_path, monkeypatch):
    legacy_data = tmp_path / "legacy-data"
    legacy_data.mkdir()
    (legacy_data / "portfolio").mkdir()
    (legacy_data / "portfolio" / "profile.md").write_text("LEGACY\n")
    # Destination already has a profile.md — should NOT overwrite
    new_profile = paths.profile_md()
    new_profile.parent.mkdir(parents=True, exist_ok=True)
    new_profile.write_text("EXISTING\n")

    _with_legacy(monkeypatch, tmp_data_dir, legacy_data, tmp_path / "none")
    r = runner.invoke(app, ["migrate", "paths"])
    assert r.exit_code == 0
    assert new_profile.read_text() == "EXISTING\n"  # preserved
