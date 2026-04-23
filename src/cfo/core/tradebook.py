"""Tradebook JSONL read/append/filter."""
import json
from datetime import datetime
from pathlib import Path

from cfo.schemas.tradebook import Trade, TradeMode
from cfo.util import atomic, paths


TERMINAL_ORDER_STATES = {"filled", "cancelled", "canceled", "failed", "rejected"}
RH_ACCOUNT_ID_MAP = {
    "597357623": "rh-individual",
    "647360304": "rh-roth",
}


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
        try:
            out.append(Trade.model_validate(json.loads(line)))
        except Exception:
            # Skip malformed legacy rows instead of breaking all read paths.
            continue
    return out


def save_all(trades: list[Trade]) -> None:
    atomic.write_jsonl(
        paths.tradebook_master(),
        [t.model_dump(mode="json", exclude_none=True) for t in trades],
    )


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


def sync_order_details(fetch_order, pending_only: bool = True) -> int:
    trades = load_all()
    changed = 0
    new_trades: list[Trade] = []
    for trade in trades:
        should_sync = bool(trade.rh_order_id) and trade.mode == TradeMode.real
        if should_sync and pending_only:
            should_sync = (trade.order_state or "").lower() not in TERMINAL_ORDER_STATES
        if not should_sync:
            new_trades.append(trade)
            continue

        rec = fetch_order(trade.rh_order_id)
        state = (rec.get("state") or "").strip().lower() or None
        updated_at = rec.get("updated_at") or None
        cumulative_quantity = rec.get("cumulative_quantity")
        average_price = rec.get("average_price")
        update = {
            "order_state": state,
            "order_updated_at": updated_at,
            "filled_qty": float(cumulative_quantity) if cumulative_quantity not in (None, "") else None,
            "fill_price": float(average_price) if average_price not in (None, "") else None,
        }
        if update["fill_price"] == 0:
            update["fill_price"] = None
        if update["filled_qty"] == 0:
            update["filled_qty"] = None
        updated_trade = Trade.model_validate({
            **trade.model_dump(mode="json", exclude_none=True),
            **{k: v for k, v in update.items() if v is not None or k in {"order_state", "order_updated_at"}},
        })
        if updated_trade.model_dump(mode="json", exclude_none=True) != trade.model_dump(mode="json", exclude_none=True):
            changed += 1
        new_trades.append(updated_trade)

    if changed:
        save_all(new_trades)
    return changed


def import_rh_trades_log(src: Path | None = None) -> int:
    src = src or paths.rh_raw_trades_jsonl()
    src = Path(src)
    if not src.exists():
        return 0

    trades = load_all()
    known_order_ids = {t.rh_order_id for t in trades if t.rh_order_id}
    imported = 0

    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        order_id = rec.get("rh_order_id") or rec.get("id")
        if not order_id or order_id in known_order_ids:
            continue

        qty = rec.get("shares") or rec.get("qty") or rec.get("quantity")
        price = rec.get("price")
        total = rec.get("notional_usd") or rec.get("total_value") or rec.get("total")
        account_number = str(rec.get("account_number") or "")
        account_id = RH_ACCOUNT_ID_MAP.get(account_number, f"rh-{account_number}" if account_number else "rh-unknown")

        trade = Trade.model_validate({
            "schema_version": 1,
            "id": order_id,
            "ts": rec.get("ts") or rec.get("created_at") or datetime.utcnow().isoformat() + "Z",
            "mode": "real",
            "account_id": account_id,
            "source": "rh",
            "symbol": (rec.get("symbol") or "").strip().upper(),
            "side": rec.get("side"),
            "qty": float(qty),
            "price": float(price) if price not in (None, "") else None,
            "total": float(total) if total not in (None, "") else None,
            "notes": rec.get("notes") or "",
            "rh_order_id": order_id,
            "order_state": (rec.get("state") or "").strip().lower() or None,
        })
        trades.append(trade)
        known_order_ids.add(order_id)
        imported += 1

    if imported:
        save_all(trades)
    return imported
