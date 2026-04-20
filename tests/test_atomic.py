import json
from pathlib import Path

import pytest

from cfo.util import atomic


def test_write_json_creates_file(tmp_path):
    target = tmp_path / "out.json"
    atomic.write_json(target, {"hello": "world"})
    assert target.exists()
    assert json.loads(target.read_text()) == {"hello": "world"}


def test_write_json_creates_parent_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "out.json"
    atomic.write_json(target, {"x": 1})
    assert target.exists()


def test_write_json_atomic_leaves_no_partial(tmp_path, monkeypatch):
    target = tmp_path / "out.json"
    target.write_text('{"existing": true}')

    import os
    real_replace = os.replace

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(RuntimeError):
        atomic.write_json(target, {"new": "data"})

    assert json.loads(target.read_text()) == {"existing": True}
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_append_jsonl_creates_file(tmp_path):
    target = tmp_path / "log.jsonl"
    atomic.append_jsonl(target, {"a": 1})
    atomic.append_jsonl(target, {"b": 2})
    lines = target.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}
