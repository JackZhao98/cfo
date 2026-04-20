"""Shared fixtures."""
import os
from pathlib import Path
import pytest


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect all cfo paths into tmp_path for isolated tests."""
    data = tmp_path / "data"
    config = tmp_path / "config-cfo"
    rh_config = tmp_path / "config-rh"
    data.mkdir()
    config.mkdir()
    rh_config.mkdir()
    monkeypatch.setenv("CFO_DATA_DIR", str(data))
    monkeypatch.setenv("CFO_CONFIG_DIR", str(config))
    monkeypatch.setenv("CFO_RH_CONFIG_DIR", str(rh_config))
    return {
        "data": data,
        "config": config,
        "rh_config": rh_config,
    }
