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
            rec = {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "ts": _to_iso(row.get("date", "")) if row.get("date") else datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "mode": row.get("mode", "real").strip() or "real",
                "account_id": row.get("account", "").strip() or "unknown",
                "source": "legacy_csv",
                "symbol": row.get("symbol", "").strip(),
                "side": row.get("side", "").strip(),
                "qty": _maybe_float(row.get("qty", "")),
                "price": _maybe_float(row.get("price", "")),
                "total": _maybe_float(row.get("total", "")),
                "strategy": (row.get("strategy") or "").strip() or None,
                "notes": (row.get("notes") or "").strip(),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    return count
