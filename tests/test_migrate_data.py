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
