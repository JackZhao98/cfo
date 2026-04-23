"""Convert legacy trades.csv to data/tradebook/master.jsonl.

Legacy columns vary — we normalize into the v1 tradebook schema:
{schema_version, id, ts, mode, account_id, source, symbol, side,
 qty, price, total, strategy, notes, rh_order_id?}
"""
import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _to_iso(d: str) -> str:
    """Accept YYYY-MM-DD and return full ISO with zero time + UTC tz."""
    dt = datetime.strptime(d.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds")


def _maybe_float(v: str) -> float | None:
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _norm_row(row: dict[str, str]) -> dict[str, str]:
    return {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}


def _account_id(raw: str, mode: str) -> str:
    label = (raw or "").strip().lower()
    mapped = {
        "trading": "rh-individual",
        "roth": "rh-roth",
    }.get(label, label or "unknown")
    if mode == "paper":
        if mapped.startswith("rh-"):
            return f"paper/{mapped[3:]}"
        return f"paper/{mapped}"
    return mapped


def _side(row: dict[str, str]) -> str:
    side = row.get("side", "").strip().upper()
    cp = row.get("cp", "").strip().upper()
    if cp == "P":
        return {
            "STO": "sell_put",
            "BTC": "buy_put",
            "BTO": "buy_put",
            "STC": "sell_put",
        }.get(side, "sell_put")
    if cp == "C":
        return {
            "STO": "sell_call",
            "BTC": "buy_call",
            "BTO": "buy_call",
            "STC": "sell_call",
        }.get(side, "sell_call")
    return {
        "BTO": "buy",
        "BUY": "buy",
        "STO": "sell",
        "STC": "sell",
        "SELL": "sell",
    }.get(side, side.lower())


def _strategy(row: dict[str, str], mode: str, symbol: str) -> str | None:
    notes = (row.get("notes") or "").lower()
    if "wheel" in notes or ("paper" == mode and symbol == "SOFI" and row.get("cp", "").upper() == "P"):
        return "wheel"
    if symbol in {"VOO", "QQQM"} and _side(row) == "buy":
        return "tiered-dca"
    return None


def convert(src_csv: Path, dst_jsonl: Path) -> int:
    """Read src CSV, write dst JSONL. Returns count of converted rows."""
    src_csv = Path(src_csv)
    dst_jsonl = Path(dst_jsonl)
    if not src_csv.exists():
        raise FileNotFoundError(src_csv)
    dst_jsonl.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with src_csv.open(newline="", encoding="utf-8") as f, dst_jsonl.open("w", encoding="utf-8") as out:
        reader = csv.DictReader(f)
        for row in reader:
            row = _norm_row(row)
            mode = (row.get("mode", "real").strip() or "real").lower()
            symbol = row.get("symbol", "").strip().upper()
            price = _maybe_float(row.get("price", ""))
            total = _maybe_float(row.get("total", "")) or _maybe_float(row.get("notional", ""))
            premium = price if row.get("cp", "").strip().upper() in {"P", "C"} else None
            rec = {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "ts": _to_iso(row.get("date", "")) if row.get("date") else datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "mode": mode,
                "account_id": _account_id(row.get("account") or row.get("acct", ""), mode),
                "source": "legacy_csv",
                "symbol": symbol,
                "side": _side(row),
                "qty": _maybe_float(row.get("qty", "")),
                "price": price,
                "total": total,
                "strategy": _strategy(row, mode, symbol),
                "notes": (row.get("notes") or "").strip(),
                "strike": _maybe_float(row.get("strike", "")),
                "exp": (row.get("expiry") or "").strip() or None,
                "premium": premium,
                "rh_order_id": (row.get("orderid") or row.get("rh_order_id") or "").strip() or None,
                "order_state": (row.get("status") or "").strip().lower() or None,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    return count
