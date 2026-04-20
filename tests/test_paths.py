from pathlib import Path
from cfo.util import paths


def test_data_dir_respects_env(tmp_data_dir):
    assert paths.data_dir() == tmp_data_dir["data"]


def test_config_dir_respects_env(tmp_data_dir):
    assert paths.config_dir() == tmp_data_dir["config"]


def test_rh_config_dir_respects_env(tmp_data_dir):
    assert paths.rh_config_dir() == tmp_data_dir["rh_config"]


def test_accounts_json_path(tmp_data_dir):
    expected = tmp_data_dir["data"] / "portfolio" / "accounts.json"
    assert paths.accounts_json() == expected


def test_profile_md_path(tmp_data_dir):
    expected = tmp_data_dir["data"] / "portfolio" / "profile.md"
    assert paths.profile_md() == expected


def test_audit_log_path(tmp_data_dir):
    expected = tmp_data_dir["data"] / "audit" / "cfo-actions.jsonl"
    assert paths.audit_log() == expected


def test_tradebook_master_path(tmp_data_dir):
    expected = tmp_data_dir["data"] / "tradebook" / "master.jsonl"
    assert paths.tradebook_master() == expected


def test_default_data_dir_without_env(monkeypatch):
    monkeypatch.delenv("CFO_DATA_DIR", raising=False)
    p = paths.data_dir()
    assert p.is_absolute()
