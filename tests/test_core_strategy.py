from datetime import date

import pytest

from cfo.core import strategy as core
from cfo.core import portfolio as portfolio_core
from cfo.schemas.portfolio import Account, AccountSource, AccountType
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
    core.set_paper_portfolio("x", "paper-x")
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


def test_set_paper_portfolio_updates_meta_and_history(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    core.set_paper_portfolio("x", "paper-x")
    meta = core.load_meta("x")
    assert meta.paper_portfolio == "paper-x"
    assert "paper_portfolio" in str(meta.history[-1])


def test_set_live_account_updates_meta_and_history(tmp_data_dir):
    portfolio_core.add_account(Account(
        id="rh-roth",
        type=AccountType.roth_ira,
        broker="robinhood",
        source=AccountSource.rh_sync,
        balance=1000,
    ))
    core.new_strategy(name="x", template="wheel")
    core.set_live_account("x", "rh-roth")
    meta = core.load_meta("x")
    assert meta.live_account == "rh-roth"
    assert "live_account" in str(meta.history[-1])


def test_set_capital_budget_updates_meta_and_history(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    core.set_capital_budget("x", 2500)
    meta = core.load_meta("x")
    assert meta.capital_budget == 2500
    assert "capital_budget" in str(meta.history[-1])


def test_set_live_account_rejects_missing_account(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    with pytest.raises(KeyError):
        core.set_live_account("x", "missing")


def test_transition_to_live_requires_bound_account(tmp_data_dir):
    core.new_strategy(name="x", template="wheel")
    core.transition("x", StrategyState.observing)
    core.set_paper_portfolio("x", "paper-x")
    core.transition("x", StrategyState.paper)
    with pytest.raises(ValueError):
        core.transition("x", StrategyState.live)


def test_transition_to_live_succeeds_after_binding(tmp_data_dir):
    portfolio_core.add_account(Account(
        id="rh-individual",
        type=AccountType.taxable,
        broker="robinhood",
        source=AccountSource.rh_sync,
        balance=1000,
    ))
    core.new_strategy(name="x", template="wheel")
    core.transition("x", StrategyState.observing)
    core.set_paper_portfolio("x", "paper-x")
    core.transition("x", StrategyState.paper)
    core.set_live_account("x", "rh-individual")
    core.transition("x", StrategyState.live)
    assert core.load_meta("x").state == StrategyState.live
