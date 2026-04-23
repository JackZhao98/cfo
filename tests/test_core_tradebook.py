import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

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


def test_sync_order_details_updates_pending_trade(tmp_data_dir):
    trade = _mk().model_copy(update={"rh_order_id": "abc", "order_state": "queued"})
    core.append(trade)

    def fetch_order(order_id: str):
        assert order_id == "abc"
        return {
            "id": "abc",
            "state": "filled",
            "updated_at": "2026-04-21T04:26:36.896359Z",
            "cumulative_quantity": 1,
            "average_price": 101.25,
        }

    changed = core.sync_order_details(fetch_order, pending_only=True)
    assert changed == 1
    updated = core.load_all()[0]
    assert updated.order_state == "filled"
    assert updated.filled_qty == 1
    assert updated.fill_price == 101.25


def test_sync_order_details_skips_terminal_when_pending_only(tmp_data_dir):
    trade = _mk().model_copy(update={"rh_order_id": "abc", "order_state": "filled"})
    core.append(trade)

    def fetch_order(order_id: str):
        raise AssertionError("should not fetch terminal orders")

    changed = core.sync_order_details(fetch_order, pending_only=True)
    assert changed == 0


def test_import_rh_trades_log_imports_missing_orders(tmp_data_dir):
    src = Path(tmp_data_dir["rh_config"]) / "trades.jsonl"
    src.write_text(
        '{"ts":"2026-04-21T05:37:41Z","rh_order_id":"oid1","account_number":"597357623","symbol":"QQQM","side":"buy","type":"MKT","tif":"GFD","shares":"0.037424","price":"267.2100","notional_usd":"10.00","state":"queued"}\n',
        encoding="utf-8",
    )
    imported = core.import_rh_trades_log(src)
    assert imported == 1
    trade = core.load_all()[0]
    assert trade.account_id == "rh-individual"
    assert trade.symbol == "QQQM"
    assert trade.rh_order_id == "oid1"
    assert trade.order_state == "queued"


def test_import_rh_trades_log_skips_existing_orders(tmp_data_dir):
    src = Path(tmp_data_dir["rh_config"]) / "trades.jsonl"
    src.write_text(
        '{"ts":"2026-04-21T05:37:41Z","rh_order_id":"oid1","account_number":"597357623","symbol":"QQQM","side":"buy","type":"MKT","tif":"GFD","shares":"0.037424","price":"267.2100","notional_usd":"10.00","state":"queued"}\n',
        encoding="utf-8",
    )
    core.append(_mk(symbol="QQQM").model_copy(update={"rh_order_id": "oid1", "order_state": "queued"}))
    imported = core.import_rh_trades_log(src)
    assert imported == 0
