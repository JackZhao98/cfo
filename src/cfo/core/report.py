"""Generate weekly / monthly markdown reports from existing cfo data."""
import json
from datetime import date, timedelta

from cfo.core import audit_query
from cfo.core import history as core_history
from cfo.core import portfolio as core_portfolio
from cfo.core import strategy as core_strategy
from cfo.core import tradebook as core_tradebook
from cfo.schemas.tradebook import Trade, TradeMode
from cfo.util import paths, timerange


def _load_trades_tolerant() -> list[Trade]:
    """Like tradebook.load_all but skips rows that fail schema validation
    (e.g. legacy_csv placeholder rows with empty side/null qty)."""
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
            # Skip malformed / legacy rows; do not fail report generation.
            continue
    return out


def _trades_between(start: date, end: date) -> list[Trade]:
    try:
        all_trades = core_tradebook.load_all()
    except Exception:
        all_trades = _load_trades_tolerant()
    return [
        t for t in all_trades
        if timerange.datetime_in_range(t.ts, start, end)
    ]


def _section_portfolio(start: date, end: date, prev_label: str, curr_label: str) -> str:
    af = core_portfolio.load()
    total = sum(a.balance for a in af.accounts)
    lines = ["## Portfolio", "", f"Current total: **${total:,.2f}**", ""]
    delta = core_history.total_delta(prev_label, curr_label)
    if delta is not None:
        arrow = "▲" if delta >= 0 else "▼"
        lines.append(f"Delta vs {prev_label}: **{arrow} ${delta:,.2f}**")
        lines.append("")
    lines.append("| Account | Type | Balance |")
    lines.append("|---|---|---:|")
    for a in af.accounts:
        lines.append(f"| {a.id} | {a.type.value} | ${a.balance:,.2f} |")
    lines.append("")
    return "\n".join(lines)


def _section_trades(start: date, end: date) -> str:
    trades = _trades_between(start, end)
    if not trades:
        lines = ["## Trades", "", f"No trades between {start} and {end}.", ""]
        return "\n".join(lines)
    real = [t for t in trades if t.mode == TradeMode.real]
    paper = [t for t in trades if t.mode == TradeMode.paper]
    lines = [
        "## Trades",
        "",
        f"{len(trades)} trade(s) — {len(real)} real, {len(paper)} paper",
        "",
        "| TS | Mode | Symbol | Side | Qty | Total | Strategy |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for t in trades:
        total = f"${t.total:,.2f}" if t.total is not None else "-"
        lines.append(
            f"| {t.ts.isoformat(timespec='minutes')} | {t.mode.value} | "
            f"{t.symbol} | {t.side.value} | {t.qty:g} | {total} | {t.strategy or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _section_strategies() -> str:
    metas = core_strategy.list_strategies()
    lines = ["## Strategies", ""]
    if not metas:
        lines.extend(["No strategies defined.", ""])
        return "\n".join(lines)
    lines.append("| Name | State | Created | Paper | Live | Budget |")
    lines.append("|---|---|---|---|---|---:|")
    for m in metas:
        lines.append(
            f"| {m.name} | {m.state.value} | {m.created_at or '-'} | "
            f"{m.paper_portfolio or '-'} | {m.live_account or '-'} | "
            f"{f'${m.capital_budget:,.2f}' if m.capital_budget is not None else '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _section_audit(start: date, end: date) -> str:
    s = audit_query.summarize(start, end)
    lines = ["## Audit", ""]
    if s["total"] == 0:
        lines.extend(["No audit records.", ""])
        return "\n".join(lines)
    lines.append(f"{s['total']} cfo invocations ({s['ok']} ok, {s['error']} error).")
    lines.append("")
    if s["by_command"]:
        lines.append("| Command | Count |")
        lines.append("|---|---:|")
        for cmd, n in sorted(s["by_command"].items(), key=lambda x: -x[1]):
            lines.append(f"| {cmd} | {n} |")
        lines.append("")
    return "\n".join(lines)


def _section_price_log(start: date, end: date) -> str:
    """List symbols snapped in range + biggest last_price delta per symbol."""
    from cfo.core import price_log as core_pl

    seen: dict[str, list[float]] = {}
    day = start
    while day <= end:
        p = core_pl._snap_file(day)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                import json as _json
                rec = _json.loads(line)
                sym = rec.get("symbol", "")
                price = rec.get("last_price")
                if sym and price is not None:
                    seen.setdefault(sym, []).append(float(price))
        day = day + timedelta(days=1)
    lines = ["## Price Log", ""]
    if not seen:
        lines.extend(["No snapshots.", ""])
        return "\n".join(lines)
    lines.append("| Symbol | Snaps | First | Last | Δ |")
    lines.append("|---|---:|---:|---:|---:|")
    for sym, prices in sorted(seen.items()):
        first = prices[0]
        last = prices[-1]
        delta = last - first
        lines.append(f"| {sym} | {len(prices)} | {first:.2f} | {last:.2f} | {delta:+.2f} |")
    lines.append("")
    return "\n".join(lines)


def weekly(today: date | None = None) -> str:
    today = today or date.today()
    start, end = timerange.iso_week_bounds(today)
    curr_id = timerange.iso_week_id(today)
    prev_id = timerange.iso_week_id(start - timedelta(days=1))
    parts = [
        f"# Weekly Report — {curr_id}",
        "",
        f"Range: **{start.isoformat()} → {end.isoformat()}**",
        "",
        _section_portfolio(start, end, prev_id, curr_id),
        _section_trades(start, end),
        _section_strategies(),
        _section_price_log(start, end),
        _section_audit(start, end),
    ]
    return "\n".join(parts).rstrip() + "\n"


def monthly(today: date | None = None) -> str:
    today = today or date.today()
    start, end = timerange.month_bounds(today)
    curr_id = timerange.month_id(today)
    prev_id = timerange.month_id(start - timedelta(days=1))
    parts = [
        f"# Monthly Report — {curr_id}",
        "",
        f"Range: **{start.isoformat()} → {end.isoformat()}**",
        "",
        _section_portfolio(start, end, prev_id, curr_id),
        _section_trades(start, end),
        _section_strategies(),
        _section_price_log(start, end),
        _section_audit(start, end),
    ]
    return "\n".join(parts).rstrip() + "\n"
