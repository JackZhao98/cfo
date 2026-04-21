"""Tests for rh_bridge subprocess wrapper."""
import json
import subprocess

import pytest

from cfo.core import rh_bridge


def test_snapshot_parses_json(monkeypatch):
    payload = {
        "total_portfolio": 16956.93,
        "total_cash": 11383.71,
        "accounts": [
            {
                "account_number": "597357623",
                "brokerage_account_type": "individual",
                "portfolio_value": 8043.00,
                "cash": 7450.38,
                "holdings": [],
            },
        ],
    }

    captured = {}

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        return Fake()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rh_bridge.snapshot()
    assert out == payload
    # Verify we invoke the correct rh flag
    assert captured["cmd"] == ["rh", "account", "snapshot", "--format", "json"]


def test_snapshot_nonzero_raises(monkeypatch):
    class Fake:
        returncode = 1
        stdout = ""
        stderr = "not logged in"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    with pytest.raises(RuntimeError) as e:
        rh_bridge.snapshot()
    assert "not logged in" in str(e.value)


def test_snapshot_invalid_json_raises(monkeypatch):
    class Fake:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    with pytest.raises(RuntimeError):
        rh_bridge.snapshot()
