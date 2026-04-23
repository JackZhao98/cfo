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


def test_quote_parses_json(monkeypatch):
    payload = {
        "symbol": "VOO",
        "last_price": 651.51,
        "bid": 652.69,
        "ask": 652.8,
        "updated_at": "2026-04-21T02:10:34Z",
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
    out = rh_bridge.quote("VOO")
    assert out == payload
    assert captured["cmd"] == ["rh", "quote", "VOO", "--format", "json"]


def test_quote_nonzero_raises(monkeypatch):
    class Fake:
        returncode = 1
        stdout = ""
        stderr = "symbol not found"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    with pytest.raises(RuntimeError) as e:
        rh_bridge.quote("BADSYM")
    assert "symbol not found" in str(e.value)


def test_quote_invalid_json_raises(monkeypatch):
    class Fake:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    with pytest.raises(RuntimeError):
        rh_bridge.quote("VOO")


def test_order_parses_json(monkeypatch):
    payload = {
        "id": "abc",
        "state": "queued",
        "updated_at": "2026-04-21T04:26:36.896359Z",
        "cumulative_quantity": 0,
        "average_price": 0,
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
    out = rh_bridge.order("abc")
    assert out == payload
    assert captured["cmd"] == ["rh", "order", "abc", "--format", "json"]


def test_order_nonzero_raises(monkeypatch):
    class Fake:
        returncode = 1
        stdout = ""
        stderr = "order not found"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    with pytest.raises(RuntimeError) as e:
        rh_bridge.order("abc")
    assert "order not found" in str(e.value)


def test_bars_parses_json(monkeypatch):
    payload = {"symbol": "SOFI", "data": [{"time": "2026-04-21 00:00", "close": 18.83}]}

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    out = rh_bridge.bars("SOFI", "2026-01-01", "2026-04-22")
    assert out == payload


def test_symbol_news_parses_json(monkeypatch):
    payload = {"symbol": "SOFI", "count": 1, "news": [{"title": "launches new product"}]}

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    out = rh_bridge.symbol_news("SOFI")
    assert out == payload


def test_symbol_earnings_parses_json(monkeypatch):
    payload = {"symbol": "SOFI", "count": 1, "events": [{"report_date": "2026-04-29"}]}

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    out = rh_bridge.symbol_earnings("SOFI")
    assert out == payload


def test_option_expirations_parses_json(monkeypatch):
    payload = {"symbol": "SOFI", "expiration_dates": ["2026-05-22"]}

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    out = rh_bridge.option_expirations("SOFI")
    assert out == payload


def test_option_chain_parses_json(monkeypatch):
    payload = {"symbol": "SOFI", "expiration_date": "2026-05-22", "options": [{"strike": 16}]}

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    out = rh_bridge.option_chain("SOFI", "2026-05-22")
    assert out == payload
