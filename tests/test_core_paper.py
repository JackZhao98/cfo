import pytest
from datetime import date

from cfo.core import paper as core
from cfo.schemas.paper import PaperKind
from cfo.util import paths


def test_create_strategy_paper(tmp_data_dir):
    from cfo.core import strategy as strategy_core

    strategy_core.new_strategy(name="wheel-sofi", template="wheel")
    core.create(kind=PaperKind.strategy, pid="wheel-sofi-2k",
                strategy_ref="wheel-sofi", capital=2000)
    d = paths.paper_strategies_dir() / "wheel-sofi-2k"
    assert (d / "meta.json").exists()
    assert (d / "portfolio.json").exists()
    assert (d / "trades.jsonl").exists()
    assert strategy_core.load_meta("wheel-sofi").paper_portfolio == "wheel-sofi-2k"


def test_create_composite(tmp_data_dir):
    core.create(kind=PaperKind.composite, pid="sim-55k", capital=55000)
    d = paths.paper_composite_dir() / "sim-55k"
    assert (d / "meta.json").exists()


def test_create_duplicate(tmp_data_dir):
    from cfo.core import strategy as strategy_core

    strategy_core.new_strategy(name="x", template="wheel")
    core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1000)
    with pytest.raises(FileExistsError):
        core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1000)


def test_list_paper(tmp_data_dir):
    from cfo.core import strategy as strategy_core

    strategy_core.new_strategy(name="x", template="wheel")
    core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1)
    core.create(kind=PaperKind.composite, pid="b", capital=2)
    all_ = core.list_all()
    ids = sorted(m.id for m in all_)
    assert ids == ["a", "b"]


def test_close_paper(tmp_data_dir):
    from cfo.core import strategy as strategy_core

    strategy_core.new_strategy(name="x", template="wheel")
    core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1)
    core.close("a")
    m = core.load_meta("a")
    assert m.status == "closed"
    assert m.closed_at == date.today()
    assert strategy_core.load_meta("x").paper_portfolio is None


def test_create_strategy_paper_requires_existing_strategy(tmp_data_dir):
    with pytest.raises(FileNotFoundError):
        core.create(kind=PaperKind.strategy, pid="a", strategy_ref="missing", capital=1000)


def test_create_strategy_paper_rejects_second_binding(tmp_data_dir):
    from cfo.core import strategy as strategy_core

    strategy_core.new_strategy(name="x", template="wheel")
    core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1000)
    with pytest.raises(ValueError):
        core.create(kind=PaperKind.strategy, pid="b", strategy_ref="x", capital=1000)
