import json

from cfo.util import audit, paths


def test_record_writes_single_line(tmp_data_dir):
    audit.record(cmd=["cfo", "portfolio", "show"], result="ok", duration_ms=5)
    log = paths.audit_log()
    assert log.exists()
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["cmd"] == ["cfo", "portfolio", "show"]
    assert rec["result"] == "ok"
    assert rec["duration_ms"] == 5
    assert "ts" in rec
    assert "+00:00" in rec["ts"]
    assert "pid" in rec


def test_record_appends(tmp_data_dir):
    audit.record(cmd=["cfo", "x"], result="ok", duration_ms=1)
    audit.record(cmd=["cfo", "y"], result="error", duration_ms=2)
    log = paths.audit_log()
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["cmd"] == ["cfo", "x"]
    assert json.loads(lines[1])["cmd"] == ["cfo", "y"]
