"""Tests for one-shot migration scripts.

These scripts live in /scripts (Robinhood repo root), but we test them
against the packaged logic module we'll create under cfo/migrations_oneshot/.
"""
import json
from pathlib import Path

from cfo.migrations_oneshot import trades_csv as mig


def test_csv_to_jsonl_basic(tmp_path):
    src = tmp_path / "trades.csv"
    src.write_text(
        "date,mode,account,symbol,side,qty,price,total,strategy,notes\n"
        "2026-04-19,real,rh-individual,VOO,buy,0.077,489.12,37.66,dca-voo,queued\n"
        "2026-04-18,paper,paper/wheel-sofi-2k,SOFI,sell_put,1,8,35,wheel-sofi,initial\n"
    )
    dst = tmp_path / "master.jsonl"
    n = mig.convert(src, dst)
    assert n == 2

    lines = dst.read_text().strip().split("\n")
    assert len(lines) == 2
    r1 = json.loads(lines[0])
    assert r1["symbol"] == "VOO"
    assert r1["qty"] == 0.077
    assert r1["mode"] == "real"
    assert r1["schema_version"] == 1
    assert "id" in r1
    assert "ts" in r1


def test_csv_missing_raises(tmp_path):
    import pytest
    dst = tmp_path / "master.jsonl"
    with pytest.raises(FileNotFoundError):
        mig.convert(tmp_path / "nope.csv", dst)


def test_jack_profile_copy(tmp_path):
    from cfo.migrations_oneshot import jack_profile as migp
    src = tmp_path / "old-profile.md"
    src.write_text("# Jack\n\nAge: 28\n\n## Accounts\n- RH: $30k\n", encoding="utf-8")
    dst = tmp_path / "out" / "profile.md"
    migp.copy(src, dst)
    assert dst.exists()
    content = dst.read_text()
    assert "Jack" in content
    assert "Migrated" in content  # banner present


def test_csv_to_jsonl_current_legacy_shape(tmp_path):
    src = tmp_path / "trades.csv"
    src.write_text(
        "Date,Time,Acct,Symbol,Side,Qty,Price,Type,TIF,Strike,Expiry,CP,Notional,Effect,Status,Mode,OrderID,Notes\n"
        "2026-04-20,10:00:00,Roth,SOFI,STO,1,0.73,LMT,GTC,17.50,2026-05-22,P,73.00,CR,OPEN,PAPER,,Wheel #1 paper\n"
        "2026-04-20,16:44:25,Trading,VOO,BTO,0.07663,652.43,MKT,GFD,,,,50.00,DR,QUEUED,REAL,abc123,Layer 3 test\n",
        encoding="utf-8",
    )
    dst = tmp_path / "master.jsonl"
    n = mig.convert(src, dst)
    assert n == 2
    lines = dst.read_text(encoding="utf-8").strip().splitlines()
    r1 = json.loads(lines[0])
    assert r1["mode"] == "paper"
    assert r1["account_id"] == "paper/roth"
    assert r1["side"] == "sell_put"
    assert r1["strategy"] == "wheel"
    assert r1["strike"] == 17.5
    assert r1["exp"] == "2026-05-22"
    r2 = json.loads(lines[1])
    assert r2["mode"] == "real"
    assert r2["account_id"] == "rh-individual"
    assert r2["side"] == "buy"
    assert r2["strategy"] == "tiered-dca"
    assert r2["rh_order_id"] == "abc123"
