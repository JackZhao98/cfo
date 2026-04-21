import pytest
from pydantic import ValidationError

from cfo.schemas.strategy import StrategyMeta, StrategyState


def test_strategy_meta_minimal():
    s = StrategyMeta(name="wheel-sofi", state=StrategyState.draft)
    assert s.schema_version == 1
    assert s.entry_rules == []


def test_state_transitions_allowed():
    # state machine enforcement is in core, schema only stores a value
    for state in StrategyState:
        StrategyMeta(name="x", state=state)


def test_meta_rejects_bad_version():
    with pytest.raises(ValidationError):
        StrategyMeta(schema_version=99, name="x", state="draft")
