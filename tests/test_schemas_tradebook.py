import pytest
from pydantic import ValidationError

from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource


def test_trade_real_buy():
    t = Trade(
        id="abc", ts="2026-04-20T09:30:00-07:00", mode=TradeMode.real,
        account_id="rh-individual", source=TradeSource.rh,
        symbol="VOO", side=TradeSide.buy, qty=0.077, price=489.12, total=37.66,
        strategy="dca-voo",
    )
    assert t.mode == TradeMode.real
    assert t.schema_version == 1


def test_trade_paper_sell_put():
    t = Trade(
        id="x", ts="2026-04-20T10:15:00-07:00", mode=TradeMode.paper,
        account_id="paper/wheel-sofi-2k", source=TradeSource.cfo,
        symbol="SOFI", side=TradeSide.sell_put, qty=1, strike=8.0,
        exp="2026-05-16", premium=0.35, total=35.0, strategy="wheel-sofi",
    )
    assert t.side == TradeSide.sell_put


def test_trade_rejects_unknown_version():
    with pytest.raises(ValidationError):
        Trade(
            schema_version=99, id="x", ts="2026-04-20T10:15:00-07:00",
            mode="real", account_id="x", source="rh",
            symbol="X", side="buy", qty=1,
        )


def test_trade_negative_qty_rejected():
    with pytest.raises(ValidationError):
        Trade(
            id="x", ts="2026-04-20T10:15:00-07:00", mode="paper",
            account_id="x", source="cfo",
            symbol="X", side="buy", qty=-1,
        )
