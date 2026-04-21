from datetime import date

from cfo.core import audit_query
from cfo.util import audit


def test_query_empty(tmp_data_dir):
    assert audit_query.query(date(2026, 4, 1), date(2026, 4, 30)) == []


def test_query_range(tmp_data_dir, monkeypatch):
    # Seed via normal audit.record calls (produces UTC timestamps)
    audit.record(cmd=["cfo", "x"], result="ok", duration_ms=1)
    audit.record(cmd=["cfo", "y"], result="error", duration_ms=2)
    today = date.today()
    recs = audit_query.query(today, today)
    assert len(recs) == 2
    assert {r["cmd"][1] for r in recs} == {"x", "y"}


def test_summarize_counts(tmp_data_dir):
    audit.record(cmd=["cfo", "portfolio", "show"], result="ok", duration_ms=1)
    audit.record(cmd=["cfo", "portfolio", "show"], result="ok", duration_ms=2)
    audit.record(cmd=["cfo", "tradebook", "add"], result="error", duration_ms=5)
    today = date.today()
    summary = audit_query.summarize(today, today)
    assert summary["total"] == 3
    assert summary["ok"] == 2
    assert summary["error"] == 1
    assert "portfolio show" in summary["by_command"]
    assert summary["by_command"]["portfolio show"] == 2


def test_summarize_empty(tmp_data_dir):
    today = date.today()
    s = audit_query.summarize(today, today)
    assert s == {"total": 0, "ok": 0, "error": 0, "by_command": {}}
