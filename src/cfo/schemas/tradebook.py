"""Tradebook schema v1 — one Trade per JSONL line."""
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, NonNegativeFloat


class TradeMode(str, Enum):
    real = "real"
    paper = "paper"


class TradeSide(str, Enum):
    buy = "buy"
    sell = "sell"
    sell_put = "sell_put"
    sell_call = "sell_call"
    buy_put = "buy_put"
    buy_call = "buy_call"


class TradeSource(str, Enum):
    rh = "rh"                # synced from rh
    cfo = "cfo"              # recorded via cfo tradebook add (paper or manual real)
    legacy_csv = "legacy_csv"


class Trade(BaseModel):
    model_config = ConfigDict(extra="allow")  # allow rh_order_id, notes, etc.
    schema_version: Literal[1] = 1
    id: str
    ts: datetime
    mode: TradeMode
    account_id: str
    source: TradeSource
    symbol: str
    side: TradeSide
    qty: NonNegativeFloat
    price: NonNegativeFloat | None = None
    total: NonNegativeFloat | None = None
    strategy: str | None = None
    notes: str = ""
    # Options fields (optional)
    strike: NonNegativeFloat | None = None
    exp: str | None = None      # YYYY-MM-DD
    premium: NonNegativeFloat | None = None
    rh_order_id: str | None = None
    order_state: str | None = None
    order_updated_at: datetime | None = None
    filled_qty: NonNegativeFloat | None = None
    fill_price: NonNegativeFloat | None = None
