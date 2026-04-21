"""Tradebook JSONL read/append/filter."""
import json
from datetime import datetime

from cfo.schemas.tradebook import Trade, TradeMode
from cfo.util import atomic, paths


def append(trade: Trade) -> None:
    atomic.append_jsonl(paths.tradebook_master(), trade.model_dump(mode="json", exclude_none=True))


def load_all() -> list[Trade]:
    p = paths.tradebook_master()
    if not p.exists():
        return []
    out: list[Trade] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(Trade.model_validate(json.loads(line)))
    return out


def filter_trades(
    mode: TradeMode | None = None,
    strategy: str | None = None,
    month: str | None = None,           # "YYYY-MM"
    symbol: str | None = None,
    account_id: str | None = None,
) -> list[Trade]:
    trades = load_all()
    if mode is not None:
        trades = [t for t in trades if t.mode == mode]
    if strategy is not None:
        trades = [t for t in trades if t.strategy == strategy]
    if symbol is not None:
        trades = [t for t in trades if t.symbol == symbol]
    if account_id is not None:
        trades = [t for t in trades if t.account_id == account_id]
    if month is not None:
        trades = [t for t in trades if t.ts.strftime("%Y-%m") == month]
    return trades
