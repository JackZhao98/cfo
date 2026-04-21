import pytest
from datetime import date

from cfo.core import paper as core
from cfo.schemas.paper import PaperKind
from cfo.util import paths


def test_create_strategy_paper(tmp_data_dir):
    core.create(kind=PaperKind.strategy, pid="wheel-sofi-2k",
                strategy_ref="wheel-sofi", capital=2000)
    d = paths.paper_strategies_dir() / "wheel-sofi-2k"
    assert (d / "meta.json").exists()
    assert (d / "portfolio.json").exists()
    assert (d / "trades.jsonl").exists()


def test_create_composite(tmp_data_dir):
    core.create(kind=PaperKind.composite, pid="sim-55k", capital=55000)
    d = paths.paper_composite_dir() / "sim-55k"
    assert (d / "meta.json").exists()


def test_create_duplicate(tmp_data_dir):
    core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1000)
    with pytest.raises(FileExistsError):
        core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1000)


def test_list_paper(tmp_data_dir):
    core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1)
    core.create(kind=PaperKind.composite, pid="b", capital=2)
    all_ = core.list_all()
    ids = sorted(m.id for m in all_)
    assert ids == ["a", "b"]


def test_close_paper(tmp_data_dir):
    core.create(kind=PaperKind.strategy, pid="a", strategy_ref="x", capital=1)
    core.close("a")
    m = core.load_meta("a")
    assert m.status == "closed"
    assert m.closed_at == date.today()
