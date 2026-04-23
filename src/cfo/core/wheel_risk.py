"""Wheel risk model for cash-secured put / wheel candidate analysis."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
import statistics
from typing import Any, Iterable, Mapping

from cfo.core import rh_bridge


POSITIVE_NEWS_WORDS = {
    "beat", "beats", "bullish", "expands", "expansion", "growth", "launch",
    "launches", "strong", "surge", "surges", "up", "upgrade", "profit",
    "profits", "record", "partnership", "approval", "momentum", "ignites",
}
NEGATIVE_NEWS_WORDS = {
    "bear", "bears", "criticize", "criticizes", "cuts", "cut", "decline",
    "declines", "dilution", "downgrade", "down", "drop", "drops", "fraud",
    "investigation", "lawsuit", "miss", "misses", "recall", "risk", "slump",
    "warn", "warning", "bankruptcy", "probe", "selloff",
}
RED_FLAG_NEWS_WORDS = {
    "fraud", "investigation", "lawsuit", "recall", "bankruptcy", "downgrade",
    "dilution", "offering", "probe",
}


@dataclass
class WheelCandidate:
    strike: float
    premium: float
    bid: float | None
    ask: float | None
    mark: float | None
    delta: float | None
    iv: float | None
    open_interest: int | None
    volume: int | None
    break_even: float
    otm_pct: float
    break_even_buffer_pct: float
    annualized_yield_pct: float
    assignment_prob: float | None
    spread_pct: float | None
    liquidity_risk: float
    assignment_risk: float
    candidate_risk: float
    wheel_fit_score: float
    notes: list[str]


@dataclass
class WheelRiskReport:
    symbol: str
    spot_price: float
    selected_expiration: str
    dte: int
    stock_risk_score: float
    stock_risk_label: str
    summary: str
    current_iv: float | None
    hv20: float | None
    hv60: float | None
    iv_hv20_ratio: float | None
    iv_rank_90d: float | None
    next_earnings_date: str | None
    days_to_earnings: int | None
    earnings_before_expiration: bool
    avg_earnings_gap_pct: float | None
    max_earnings_gap_pct: float | None
    news_sentiment: float
    news_risk: float
    news_heat_72h: int
    vix: float | None
    components: dict[str, float]
    top_candidates: list[WheelCandidate]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["top_candidates"] = [asdict(c) for c in self.top_candidates]
        return payload


@dataclass
class WheelBacktestRow:
    strike: float
    break_even: float
    dte: int
    wheel_fit_score: float
    annualized_yield_pct: float
    sample_count: int
    strike_breach_rate: float
    break_even_breach_rate: float
    assigned_rate: float
    finish_above_break_even_rate: float
    avg_terminal_return_pct: float
    worst_window_drawdown_pct: float


@dataclass
class WheelBacktestReport:
    symbol: str
    lookback_days: int
    expiration: str
    dte: int
    evaluation_count: int
    source_summary: str
    current_stock_risk_score: float
    current_stock_risk_label: str
    rows: list[WheelBacktestRow]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rows"] = [asdict(r) for r in self.rows]
        return payload


def analyze_symbol(
    symbol: str,
    *,
    expiration: str | None = None,
    min_dte: int = 21,
    max_dte: int = 60,
    limit: int = 6,
) -> WheelRiskReport:
    symbol = symbol.upper()
    today = datetime.now(timezone.utc).date()

    quote = rh_bridge.quote(symbol)
    expirations_payload = rh_bridge.option_expirations(symbol)
    selected_exp = expiration or _select_expiration(
        expirations_payload.get("expiration_dates", []),
        today=today,
        min_dte=min_dte,
        max_dte=max_dte,
    )
    if not selected_exp:
        raise RuntimeError(
            f"no option expiration available for {symbol} in {min_dte}-{max_dte} DTE"
        )

    option_chain = rh_bridge.option_chain(symbol, selected_exp, option_type="put")
    bars = rh_bridge.bars(
        symbol,
        from_date=(today - timedelta(days=370)).isoformat(),
        to_date=today.isoformat(),
        interval="day",
    )
    news = rh_bridge.symbol_news(symbol)
    earnings = rh_bridge.symbol_earnings(symbol)
    try:
        vix_rows = rh_bridge.index_values(["VIX"])
        vix = _first_float(vix_rows[0].get("value")) if vix_rows else None
    except Exception:
        vix = None

    return analyze_payloads(
        symbol=symbol,
        quote=quote,
        bars=bars,
        option_chain=option_chain,
        news=news,
        earnings=earnings,
        expiration=selected_exp,
        limit=limit,
        vix=vix,
        today=today,
    )


def analyze_payloads(
    *,
    symbol: str,
    quote: Mapping[str, Any],
    bars: Mapping[str, Any],
    option_chain: Mapping[str, Any],
    news: Mapping[str, Any],
    earnings: Mapping[str, Any],
    expiration: str,
    limit: int,
    vix: float | None,
    today: date | None = None,
) -> WheelRiskReport:
    today = today or datetime.now(timezone.utc).date()
    spot = _first_float(quote.get("current_price")) or _first_float(quote.get("last_price"))
    if spot is None or spot <= 0:
        raise RuntimeError(f"missing spot price for {symbol}")

    expiration_date = _parse_date(expiration)
    dte = max((expiration_date - today).days, 0)
    if dte <= 0:
        raise RuntimeError(f"expiration {expiration} is not in the future")

    bar_rows = bars.get("data", [])
    closes = [_first_float(row.get("close")) for row in bar_rows if _first_float(row.get("close"))]
    hv20 = _annualized_vol(closes, 20)
    hv60 = _annualized_vol(closes, 60)
    price_stats = _price_stats(bar_rows, spot)

    options = [row for row in option_chain.get("options", []) if isinstance(row, Mapping)]
    otm_puts = [row for row in options if _first_float(row.get("strike")) and _first_float(row.get("strike")) < spot]
    if not otm_puts:
        raise RuntimeError(f"no OTM puts found for {symbol} {expiration}")
    current_iv = _representative_iv(otm_puts)
    iv_rank_90d = _historical_iv_rank(symbol, current_iv)
    iv_hv20_ratio = (current_iv / hv20) if current_iv and hv20 and hv20 > 0 else None

    earnings_profile = _earnings_profile(earnings.get("events", []), bar_rows, expiration_date, today)
    news_profile = _news_profile(news.get("news", []), today)

    components = {
        "realized_vol_risk": _realized_vol_risk(hv20, hv60),
        "trend_risk": _trend_risk(price_stats),
        "earnings_risk": _earnings_risk(earnings_profile, dte),
        "news_risk": news_profile["risk"],
        "iv_regime_risk": _iv_regime_risk(current_iv, hv20, iv_rank_90d),
        "market_regime_risk": _market_regime_risk(vix),
    }
    stock_risk = round(
        0.24 * components["realized_vol_risk"]
        + 0.19 * components["trend_risk"]
        + 0.23 * components["earnings_risk"]
        + 0.12 * components["news_risk"]
        + 0.14 * components["iv_regime_risk"]
        + 0.08 * components["market_regime_risk"],
        1,
    )
    stock_label = _risk_label(stock_risk)

    candidate_pool = _candidate_pool(otm_puts, spot=spot)
    candidates = [
        _build_candidate(
            option=row,
            spot=spot,
            dte=dte,
            stock_risk=stock_risk,
            hv20=hv20,
            earnings_profile=earnings_profile,
        )
        for row in candidate_pool
    ]
    candidates = [c for c in candidates if c is not None]
    candidates.sort(key=lambda c: (-c.wheel_fit_score, c.candidate_risk, -c.annualized_yield_pct))

    summary = _summary_line(
        stock_label=stock_label,
        stock_risk=stock_risk,
        earnings_profile=earnings_profile,
        news_profile=news_profile,
        iv_hv20_ratio=iv_hv20_ratio,
    )
    return WheelRiskReport(
        symbol=symbol,
        spot_price=round(spot, 4),
        selected_expiration=expiration,
        dte=dte,
        stock_risk_score=stock_risk,
        stock_risk_label=stock_label,
        summary=summary,
        current_iv=round(current_iv, 4) if current_iv is not None else None,
        hv20=round(hv20, 4) if hv20 is not None else None,
        hv60=round(hv60, 4) if hv60 is not None else None,
        iv_hv20_ratio=round(iv_hv20_ratio, 3) if iv_hv20_ratio is not None else None,
        iv_rank_90d=round(iv_rank_90d, 1) if iv_rank_90d is not None else None,
        next_earnings_date=earnings_profile["next_date"],
        days_to_earnings=earnings_profile["days_to_next"],
        earnings_before_expiration=earnings_profile["before_expiration"],
        avg_earnings_gap_pct=earnings_profile["avg_gap_pct"],
        max_earnings_gap_pct=earnings_profile["max_gap_pct"],
        news_sentiment=round(news_profile["sentiment"], 3),
        news_risk=round(news_profile["risk"], 1),
        news_heat_72h=news_profile["heat_72h"],
        vix=round(vix, 2) if vix is not None else None,
        components={k: round(v, 1) for k, v in components.items()},
        top_candidates=candidates[:limit],
    )


def backtest_symbol(
    symbol: str,
    *,
    expiration: str | None = None,
    min_dte: int = 21,
    max_dte: int = 60,
    candidate_limit: int = 3,
    lookback_days: int = 252,
) -> WheelBacktestReport:
    risk = analyze_symbol(
        symbol,
        expiration=expiration,
        min_dte=min_dte,
        max_dte=max_dte,
        limit=candidate_limit,
    )
    today = datetime.now(timezone.utc).date()
    bars = rh_bridge.bars(
        symbol.upper(),
        from_date=(today - timedelta(days=max(lookback_days + 40, 370))).isoformat(),
        to_date=today.isoformat(),
        interval="day",
    )
    return backtest_from_bars(
        risk,
        bars=bars,
        lookback_days=lookback_days,
    )


def backtest_from_bars(
    risk: WheelRiskReport,
    *,
    bars: Mapping[str, Any],
    lookback_days: int = 252,
) -> WheelBacktestReport:
    series = _bar_series(bars.get("data", []))
    if len(series) <= risk.dte + 1:
        raise RuntimeError(
            f"not enough bars to backtest {risk.symbol}: need > {risk.dte + 1}, got {len(series)}"
        )

    if lookback_days > 0 and len(series) > lookback_days + risk.dte + 1:
        series = series[-(lookback_days + risk.dte + 1):]

    rows: list[WheelBacktestRow] = []
    evaluation_count = max(0, len(series) - risk.dte)
    for candidate in risk.top_candidates:
        stats = _candidate_path_stats(
            series=series,
            dte=risk.dte,
            current_spot=risk.spot_price,
            strike_ratio=candidate.strike / risk.spot_price,
            break_even_ratio=candidate.break_even / risk.spot_price,
        )
        rows.append(
            WheelBacktestRow(
                strike=candidate.strike,
                break_even=candidate.break_even,
                dte=risk.dte,
                wheel_fit_score=candidate.wheel_fit_score,
                annualized_yield_pct=candidate.annualized_yield_pct,
                sample_count=stats["sample_count"],
                strike_breach_rate=stats["strike_breach_rate"],
                break_even_breach_rate=stats["break_even_breach_rate"],
                assigned_rate=stats["assigned_rate"],
                finish_above_break_even_rate=stats["finish_above_break_even_rate"],
                avg_terminal_return_pct=stats["avg_terminal_return_pct"],
                worst_window_drawdown_pct=stats["worst_window_drawdown_pct"],
            )
        )
    return WheelBacktestReport(
        symbol=risk.symbol,
        lookback_days=lookback_days,
        expiration=risk.selected_expiration,
        dte=risk.dte,
        evaluation_count=evaluation_count,
        source_summary=(
            "Path-only approximation. Preserves current moneyness and break-even ratio, "
            "then replays them across historical close paths. No historical option premium reconstruction."
        ),
        current_stock_risk_score=risk.stock_risk_score,
        current_stock_risk_label=risk.stock_risk_label,
        rows=rows,
    )


def _build_candidate(
    *,
    option: Mapping[str, Any],
    spot: float,
    dte: int,
    stock_risk: float,
    hv20: float | None,
    earnings_profile: Mapping[str, Any],
) -> WheelCandidate | None:
    strike = _first_float(option.get("strike"))
    mark = _first_float(option.get("mark"))
    bid = _first_float(option.get("bid"))
    ask = _first_float(option.get("ask"))
    delta = _first_float(option.get("delta"))
    iv = _first_float(option.get("iv"))
    if strike is None or mark is None or strike <= 0 or mark <= 0:
        return None

    premium = mark
    break_even = strike - premium
    otm_pct = max((spot - strike) / spot, 0.0)
    break_even_buffer_pct = max((spot - break_even) / spot, 0.0)
    annualized_yield_pct = premium / strike * 365 / dte * 100
    assignment_prob = abs(delta) if delta is not None else None
    spread_pct = None
    if bid is not None and ask is not None and mark > 0:
        spread_pct = max(ask - bid, 0.0) / mark

    liquidity_risk = _liquidity_risk(
        spread_pct=spread_pct,
        open_interest=_first_int(option.get("open_interest")),
        volume=_first_int(option.get("volume")),
    )
    assignment_risk = min((assignment_prob or 0.5) * 100, 100)
    cushion_risk = 100 * (1 - _clamp01((break_even_buffer_pct - 0.04) / 0.16))
    candidate_risk = (
        0.48 * stock_risk
        + 0.23 * assignment_risk
        + 0.14 * liquidity_risk
        + 0.15 * cushion_risk
    )
    notes: list[str] = []
    if earnings_profile.get("before_expiration"):
        candidate_risk += 10
        notes.append("spans earnings")
    if spread_pct is not None and spread_pct > 0.45:
        notes.append("wide spread")
    if (_first_int(option.get("open_interest")) or 0) < 100:
        notes.append("thin OI")
    if assignment_prob is not None and assignment_prob > 0.30:
        notes.append("high assignment")

    iv_edge = (iv / hv20) if iv and hv20 and hv20 > 0 else None
    reward = 40 * _clamp01(annualized_yield_pct / 35) + 30 * _clamp01(break_even_buffer_pct / 0.18)
    if iv_edge is not None:
        reward += 20 * _clamp01((iv_edge - 1.0) / 1.0)
    reward += 10 * (1 - liquidity_risk / 100)
    wheel_fit = _clamp(0.55 * (100 - _clamp(candidate_risk, 0, 100)) + 0.45 * reward, 0, 100)
    return WheelCandidate(
        strike=round(strike, 2),
        premium=round(premium, 3),
        bid=round(bid, 3) if bid is not None else None,
        ask=round(ask, 3) if ask is not None else None,
        mark=round(mark, 3) if mark is not None else None,
        delta=round(delta, 4) if delta is not None else None,
        iv=round(iv, 4) if iv is not None else None,
        open_interest=_first_int(option.get("open_interest")),
        volume=_first_int(option.get("volume")),
        break_even=round(break_even, 3),
        otm_pct=round(otm_pct * 100, 2),
        break_even_buffer_pct=round(break_even_buffer_pct * 100, 2),
        annualized_yield_pct=round(annualized_yield_pct, 2),
        assignment_prob=round(assignment_prob * 100, 2) if assignment_prob is not None else None,
        spread_pct=round(spread_pct * 100, 2) if spread_pct is not None else None,
        liquidity_risk=round(liquidity_risk, 1),
        assignment_risk=round(assignment_risk, 1),
        candidate_risk=round(_clamp(candidate_risk, 0, 100), 1),
        wheel_fit_score=round(wheel_fit, 1),
        notes=notes,
    )


def _summary_line(
    *,
    stock_label: str,
    stock_risk: float,
    earnings_profile: Mapping[str, Any],
    news_profile: Mapping[str, Any],
    iv_hv20_ratio: float | None,
) -> str:
    parts = [f"{stock_label} risk ({stock_risk:.1f}/100)"]
    if earnings_profile.get("before_expiration"):
        parts.append("next earnings lands before expiration")
    elif earnings_profile.get("days_to_next") is not None:
        parts.append(f"earnings in {earnings_profile['days_to_next']}d")
    if iv_hv20_ratio is not None:
        parts.append(f"IV/HV20 {iv_hv20_ratio:.2f}x")
    if news_profile["heat_72h"] >= 5:
        parts.append(f"{news_profile['heat_72h']} recent headlines")
    if news_profile["red_flags"] > 0:
        parts.append(f"{news_profile['red_flags']} red-flag headlines")
    return "; ".join(parts)


def _select_expiration(
    expirations: Iterable[str],
    *,
    today: date,
    min_dte: int,
    max_dte: int,
) -> str | None:
    candidates: list[tuple[int, str]] = []
    fallback: list[tuple[int, str]] = []
    for exp in expirations:
        try:
            exp_date = _parse_date(exp)
        except ValueError:
            continue
        dte = (exp_date - today).days
        if dte <= 0:
            continue
        fallback.append((abs(dte - 35), exp))
        if min_dte <= dte <= max_dte:
            candidates.append((abs(dte - 35), exp))
    pool = candidates or fallback
    if not pool:
        return None
    pool.sort(key=lambda item: item[0])
    return pool[0][1]


def _candidate_pool(options: list[Mapping[str, Any]], *, spot: float) -> list[Mapping[str, Any]]:
    def good_enough(row: Mapping[str, Any], *, min_delta: float, max_delta: float) -> bool:
        strike = _first_float(row.get("strike")) or 0.0
        delta = abs(_first_float(row.get("delta")) or 0.0)
        bid = _first_float(row.get("bid")) or 0.0
        ask = _first_float(row.get("ask")) or 0.0
        mark = _first_float(row.get("mark")) or 0.0
        return (
            strike >= spot * 0.70
            and mark >= 0.03
            and bid > 0
            and ask > 0
            and min_delta <= delta <= max_delta
        )

    primary = [row for row in options if good_enough(row, min_delta=0.05, max_delta=0.35)]
    if primary:
        return primary
    secondary = [row for row in options if good_enough(row, min_delta=0.03, max_delta=0.45)]
    return secondary or options


def _bar_series(rows: list[Mapping[str, Any]]) -> list[tuple[date, float]]:
    series: list[tuple[date, float]] = []
    for row in rows:
        day = _parse_bar_date(row.get("time"))
        close = _first_float(row.get("close"))
        if day is None or close is None or close <= 0:
            continue
        series.append((day, close))
    series.sort(key=lambda item: item[0])
    return series


def _candidate_path_stats(
    *,
    series: list[tuple[date, float]],
    dte: int,
    current_spot: float,
    strike_ratio: float,
    break_even_ratio: float,
) -> dict[str, float | int]:
    sample_count = 0
    strike_breaches = 0
    break_even_breaches = 0
    assigned = 0
    finish_above_break_even = 0
    terminal_returns: list[float] = []
    worst_drawdowns: list[float] = []

    for idx in range(0, len(series) - dte):
        entry_spot = series[idx][1]
        strike = entry_spot * strike_ratio
        break_even = entry_spot * break_even_ratio
        future = [close for _, close in series[idx + 1: idx + dte + 1]]
        if len(future) < dte:
            continue
        min_close = min(future)
        terminal_close = future[-1]
        sample_count += 1

        if min_close <= strike:
            strike_breaches += 1
        if min_close <= break_even:
            break_even_breaches += 1
        if terminal_close <= strike:
            assigned += 1
        if terminal_close > break_even:
            finish_above_break_even += 1

        terminal_returns.append(terminal_close / entry_spot - 1)
        worst_drawdowns.append(min_close / entry_spot - 1)

    if sample_count == 0:
        return {
            "sample_count": 0,
            "strike_breach_rate": 0.0,
            "break_even_breach_rate": 0.0,
            "assigned_rate": 0.0,
            "finish_above_break_even_rate": 0.0,
            "avg_terminal_return_pct": 0.0,
            "worst_window_drawdown_pct": 0.0,
        }

    return {
        "sample_count": sample_count,
        "strike_breach_rate": round(strike_breaches / sample_count * 100, 2),
        "break_even_breach_rate": round(break_even_breaches / sample_count * 100, 2),
        "assigned_rate": round(assigned / sample_count * 100, 2),
        "finish_above_break_even_rate": round(finish_above_break_even / sample_count * 100, 2),
        "avg_terminal_return_pct": round(statistics.fmean(terminal_returns) * 100, 2),
        "worst_window_drawdown_pct": round(min(worst_drawdowns) * 100, 2),
    }


def _annualized_vol(closes: list[float], window: int) -> float | None:
    if len(closes) < window + 1:
        return None
    returns: list[float] = []
    for prev, curr in zip(closes[-window - 1:-1], closes[-window:]):
        if prev <= 0 or curr <= 0:
            continue
        returns.append(math.log(curr / prev))
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(252)


def _price_stats(bars: list[Mapping[str, Any]], spot: float) -> dict[str, float | None]:
    closes: list[float] = []
    for row in bars:
        close = _first_float(row.get("close"))
        if close is not None:
            closes.append(close)
    if not closes:
        return {"drawdown_52w": None, "sma20_gap": None, "sma60_gap": None, "ret20": None}
    sma20 = statistics.fmean(closes[-20:]) if len(closes) >= 20 else statistics.fmean(closes)
    sma60 = statistics.fmean(closes[-60:]) if len(closes) >= 60 else statistics.fmean(closes)
    ret20 = None
    if len(closes) >= 21 and closes[-21] > 0:
        ret20 = closes[-1] / closes[-21] - 1
    high_52w = max(closes)
    drawdown_52w = 1 - spot / high_52w if high_52w > 0 else None
    return {
        "drawdown_52w": drawdown_52w,
        "sma20_gap": (spot / sma20 - 1) if sma20 > 0 else None,
        "sma60_gap": (spot / sma60 - 1) if sma60 > 0 else None,
        "ret20": ret20,
    }


def _earnings_profile(
    events: list[Mapping[str, Any]],
    bars: list[Mapping[str, Any]],
    expiration_date: date,
    today: date,
) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    next_date: date | None = None
    days_to_next: int | None = None
    before_expiration = False
    gap_moves: list[float] = []

    trading_days: list[tuple[date, float]] = []
    for row in bars:
        close = _first_float(row.get("close"))
        bar_date = _parse_bar_date(row.get("time"))
        if close is None or bar_date is None:
            continue
        trading_days.append((bar_date, close))
    trading_days.sort(key=lambda item: item[0])

    for event in events:
        report_date_raw = event.get("report_date")
        if not report_date_raw:
            continue
        try:
            report_date = _parse_date(str(report_date_raw))
        except ValueError:
            continue
        event_dt = _earnings_event_dt_utc(report_date, str(event.get("timing") or "am"))
        if event_dt >= now_utc and next_date is None:
            next_date = report_date
            days_to_next = max((event_dt.date() - today).days, 0)
            before_expiration = report_date <= expiration_date
        move = _earnings_gap_move(trading_days, report_date, str(event.get("timing") or "am"))
        if move is not None:
            gap_moves.append(move)

    avg_gap = statistics.fmean(gap_moves) if gap_moves else None
    max_gap = max(gap_moves) if gap_moves else None
    return {
        "next_date": next_date.isoformat() if next_date else None,
        "days_to_next": days_to_next,
        "before_expiration": before_expiration,
        "avg_gap_pct": round(avg_gap * 100, 2) if avg_gap is not None else None,
        "max_gap_pct": round(max_gap * 100, 2) if max_gap is not None else None,
    }


def _earnings_gap_move(
    trading_days: list[tuple[date, float]],
    report_date: date,
    timing: str,
) -> float | None:
    if len(trading_days) < 2:
        return None
    idx = None
    for i, (day, _) in enumerate(trading_days):
        if day >= report_date:
            idx = i
            break
    if idx is None:
        return None
    if timing.lower() == "pm":
        if trading_days[idx][0] != report_date or idx + 1 >= len(trading_days):
            return None
        base = trading_days[idx][1]
        target = trading_days[idx + 1][1]
    else:
        if idx == 0:
            return None
        base = trading_days[idx - 1][1]
        target = trading_days[idx][1]
    if base <= 0:
        return None
    return abs(target / base - 1)


def _earnings_event_dt_utc(report_date: date, timing: str) -> datetime:
    timing = timing.lower().strip()
    if timing == "pm":
        # Approximate post-close publication at 4:00 PM ET.
        return datetime.combine(report_date, time(hour=20, minute=0), tzinfo=timezone.utc)
    # Approximate pre-market publication at 8:00 AM ET.
    return datetime.combine(report_date, time(hour=12, minute=0), tzinfo=timezone.utc)


def _news_profile(items: list[Mapping[str, Any]], today: date) -> dict[str, Any]:
    scores: list[float] = []
    heat_72h = 0
    red_flags = 0
    for item in items:
        text = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
        pos_hits = sum(1 for word in POSITIVE_NEWS_WORDS if word in text)
        neg_hits = sum(1 for word in NEGATIVE_NEWS_WORDS if word in text)
        if pos_hits or neg_hits:
            scores.append((pos_hits - neg_hits) / (pos_hits + neg_hits))
        published = item.get("published_at")
        if published:
            try:
                published_date = _parse_datetime(str(published)).date()
                if (today - published_date).days <= 3:
                    heat_72h += 1
            except ValueError:
                pass
        if any(word in text for word in RED_FLAG_NEWS_WORDS):
            red_flags += 1
    sentiment = statistics.fmean(scores) if scores else 0.0
    risk = 25 + max(-sentiment, 0.0) * 45 + min(heat_72h, 8) * 4 + red_flags * 10
    return {
        "sentiment": _clamp(sentiment, -1, 1),
        "risk": _clamp(risk, 0, 100),
        "heat_72h": heat_72h,
        "red_flags": red_flags,
    }


def _representative_iv(options: list[Mapping[str, Any]]) -> float | None:
    ranked: list[tuple[float, float]] = []
    for row in options:
        delta = abs(_first_float(row.get("delta")) or 0.0)
        iv = _first_float(row.get("iv"))
        if iv is None:
            continue
        ranked.append((abs(delta - 0.25), iv))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def _historical_iv_rank(symbol: str, current_iv: float | None) -> float | None:
    if current_iv is None:
        return None
    try:
        from cfo.market_db.connection import connect
    except Exception:
        return None

    ivs: list[float] = []
    try:
        with connect(read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT iv, delta, expiration, ts
                  FROM option_chain
                 WHERE symbol = ? AND type = 'put' AND iv IS NOT NULL
                 ORDER BY ts DESC
                 LIMIT 3000
                """,
                (symbol,),
            ).fetchall()
    except Exception:
        return None

    for row in rows:
        iv = _first_float(row["iv"])
        delta = abs(_first_float(row["delta"]) or 0.0)
        if iv is None:
            continue
        if delta and not (0.10 <= delta <= 0.35):
            continue
        try:
            exp = _parse_date(str(row["expiration"]))
            ts_day = _parse_date(str(row["ts"])[:10])
        except ValueError:
            continue
        dte = (exp - ts_day).days
        if 21 <= dte <= 60:
            ivs.append(iv)

    if len(ivs) < 10:
        return None
    lower = sum(1 for iv in ivs if iv <= current_iv)
    return lower / len(ivs) * 100


def _realized_vol_risk(hv20: float | None, hv60: float | None) -> float:
    vol = max(hv20 or 0.0, hv60 or 0.0)
    return _clamp01((vol - 0.22) / 0.68) * 100


def _trend_risk(price_stats: Mapping[str, float | None]) -> float:
    risk = 20.0
    sma20_gap = price_stats.get("sma20_gap")
    sma60_gap = price_stats.get("sma60_gap")
    ret20 = price_stats.get("ret20")
    drawdown_52w = price_stats.get("drawdown_52w")
    if sma20_gap is not None and sma20_gap < 0:
        risk += _clamp01(abs(sma20_gap) / 0.12) * 20
    if sma60_gap is not None and sma60_gap < 0:
        risk += _clamp01(abs(sma60_gap) / 0.18) * 20
    if ret20 is not None and ret20 < 0:
        risk += _clamp01(abs(ret20) / 0.20) * 20
    if drawdown_52w is not None:
        risk += _clamp01(drawdown_52w / 0.55) * 20
    return _clamp(risk, 0, 100)


def _earnings_risk(earnings_profile: Mapping[str, Any], dte: int) -> float:
    risk = 10.0
    days = earnings_profile.get("days_to_next")
    avg_gap = earnings_profile.get("avg_gap_pct")
    max_gap = earnings_profile.get("max_gap_pct")
    if avg_gap is not None:
        risk += _clamp01(avg_gap / 12) * 20
    if max_gap is not None:
        risk += _clamp01(max_gap / 18) * 15
    if days is not None:
        risk += max(0.0, (21 - min(days, 21)) / 21) * 30
    if earnings_profile.get("before_expiration"):
        risk += 25
    elif days is not None and days <= dte + 7:
        risk += 10
    return _clamp(risk, 0, 100)


def _iv_regime_risk(current_iv: float | None, hv20: float | None, iv_rank_90d: float | None) -> float:
    risk = 25.0
    if current_iv is not None:
        risk += _clamp01((current_iv - 0.35) / 0.75) * 35
    if current_iv is not None and hv20 and hv20 > 0:
        risk += _clamp01((current_iv / hv20 - 1.1) / 1.0) * 25
    if iv_rank_90d is not None:
        risk += _clamp01((iv_rank_90d - 60) / 40) * 15
    return _clamp(risk, 0, 100)


def _market_regime_risk(vix: float | None) -> float:
    if vix is None:
        return 25.0
    return _clamp01((vix - 16) / 19) * 100


def _liquidity_risk(*, spread_pct: float | None, open_interest: int | None, volume: int | None) -> float:
    risk = 10.0
    if spread_pct is not None:
        risk += _clamp01((spread_pct - 0.12) / 0.60) * 45
    else:
        risk += 20
    oi = open_interest or 0
    vol = volume or 0
    risk += _clamp01((100 - min(oi, 100)) / 100) * 20
    risk += _clamp01((20 - min(vol, 20)) / 20) * 15
    return _clamp(risk, 0, 100)


def _risk_label(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _parse_bar_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _first_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
