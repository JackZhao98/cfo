import json
import uuid
from datetime import datetime, timezone

import pytest

from cfo.core import tradebook as core
from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource
from cfo.util import paths


def _mk(symbol="VOO", mode=TradeMode.real, source=TradeSource.rh, side=TradeSide.buy):
    return Trade(
        id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc),
        mode=mode,
        account_id="rh-individual" if mode == TradeMode.real else "paper/x",
        source=source,
        symbol=symbol,
        side=side,
        qty=1.0,
        price=100.0,
        total=100.0,
    )


def test_append_and_load(tmp_data_dir):
    core.append(_mk())
    core.append(_mk(symbol="NVDA"))
    trades = core.load_all()
    assert len(trades) == 2
    assert trades[0].symbol == "VOO"
    assert trades[1].symbol == "NVDA"


def test_load_missing_returns_empty(tmp_data_dir):
    assert core.load_all() == []


def test_filter_by_mode(tmp_data_dir):
    core.append(_mk(symbol="VOO", mode=TradeMode.real, source=TradeSource.rh))
    core.append(_mk(symbol="SOFI", mode=TradeMode.paper, source=TradeSource.cfo))
    real = core.filter_trades(mode=TradeMode.real)
    assert len(real) == 1 and real[0].symbol == "VOO"
    paper = core.filter_trades(mode=TradeMode.paper)
    assert len(paper) == 1 and paper[0].symbol == "SOFI"


def test_filter_by_strategy(tmp_data_dir):
    t1 = _mk(symbol="SOFI", mode=TradeMode.paper, source=TradeSource.cfo)
    t1_copy = t1.model_copy(update={"strategy": "wheel-sofi"})
    core.append(t1_copy)
    core.append(_mk(symbol="VOO"))
    wheel = core.filter_trades(strategy="wheel-sofi")
    assert len(wheel) == 1 and wheel[0].symbol == "SOFI"


def test_filter_by_month(tmp_data_dir):
    core.append(_mk().model_copy(update={"ts": datetime(2026, 3, 15, tzinfo=timezone.utc)}))
    core.append(_mk(symbol="NVDA").model_copy(update={"ts": datetime(2026, 4, 10, tzinfo=timezone.utc)}))
    apr = core.filter_trades(month="2026-04")
    assert len(apr) == 1 and apr[0].symbol == "NVDA"
