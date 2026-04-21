from datetime import date

import pytest

from cfo.core import strategy as core
from cfo.schemas.strategy import StrategyMeta, StrategyState
from cfo.util import paths


def test_new_creates_yaml_and_md(tmp_data_dir):
    core.new_strategy(name="wheel-sofi", template="wheel")
    yaml_path = paths.strategies_dir() / "wheel-sofi.yaml"
    md_path = paths.strategies_dir() / "wheel-sofi.md"
    assert yaml_path.exists()
    assert md_path.exists()
    meta = core.load_meta("wheel-sofi")
    assert meta.state == StrategyState.draft


def test_duplicate_rejected(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    with pytest.raises(FileExistsError):
        core.new_strategy(name="x", template="wheel")


def test_list_strategies(tmp_data_dir):
    core.new_strategy(name="a", template="wheel")
    core.new_strategy(name="b", template="wheel")
    names = sorted([m.name for m in core.list_strategies()])
    assert names == ["a", "b"]


def test_transition_allowed(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    core.transition("x", StrategyState.observing)
    assert core.load_meta("x").state == StrategyState.observing
    core.transition("x", StrategyState.paper)
    assert core.load_meta("x").state == StrategyState.paper


def test_transition_rejected(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    # draft → live not allowed (must go through observing/paper)
    with pytest.raises(ValueError):
        core.transition("x", StrategyState.live)


def test_transition_history_appended(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    core.transition("x", StrategyState.observing)
    meta = core.load_meta("x")
    # at least 2 history entries: created + transition
    assert len(meta.history) >= 2
    assert "observing" in str(meta.history[-1])
