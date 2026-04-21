"""Tests for rh_bridge subprocess wrapper."""
import json
import subprocess

import pytest

from cfo.core import rh_bridge


def test_snapshot_parses_json(monkeypatch):
    payload = {
        "accounts": [
            {"id": "individual", "type": "taxable", "balance": 30000, "cash": 100, "holdings": []},
        ],
    }

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    def fake_run(*args, **kwargs):
        return Fake()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rh_bridge.snapshot()
    assert out == payload


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
