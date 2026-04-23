from cfo.core.wheel_risk import (
    WheelBacktestReport,
    WheelCandidate,
    WheelRiskReport,
    backtest_from_bars,
)


def test_backtest_from_bars_reports_breach_rates():
    risk = WheelRiskReport(
        symbol="SOFI",
        spot_price=20.0,
        selected_expiration="2026-05-29",
        dte=3,
        stock_risk_score=42.0,
        stock_risk_label="medium",
        summary="medium",
        current_iv=0.7,
        hv20=0.4,
        hv60=0.35,
        iv_hv20_ratio=1.75,
        iv_rank_90d=60.0,
        next_earnings_date=None,
        days_to_earnings=None,
        earnings_before_expiration=False,
        avg_earnings_gap_pct=None,
        max_earnings_gap_pct=None,
        news_sentiment=0.0,
        news_risk=25.0,
        news_heat_72h=0,
        vix=18.0,
        components={},
        top_candidates=[
            WheelCandidate(
                strike=18.0,
                premium=0.5,
                bid=0.45,
                ask=0.55,
                mark=0.5,
                delta=-0.2,
                iv=0.7,
                open_interest=100,
                volume=20,
                break_even=17.5,
                otm_pct=10.0,
                break_even_buffer_pct=12.5,
                annualized_yield_pct=33.0,
                assignment_prob=20.0,
                spread_pct=20.0,
                liquidity_risk=15.0,
                assignment_risk=20.0,
                candidate_risk=40.0,
                wheel_fit_score=65.0,
                notes=[],
            )
        ],
    )
    bars = {
        "data": [
            {"time": "2026-01-01 00:00", "close": 20.0},
            {"time": "2026-01-02 00:00", "close": 19.0},
            {"time": "2026-01-03 00:00", "close": 18.0},
            {"time": "2026-01-04 00:00", "close": 17.0},
            {"time": "2026-01-05 00:00", "close": 19.0},
            {"time": "2026-01-06 00:00", "close": 18.5},
            {"time": "2026-01-07 00:00", "close": 18.2},
        ]
    }
    report = backtest_from_bars(risk, bars=bars, lookback_days=30)
    assert isinstance(report, WheelBacktestReport)
    assert report.evaluation_count == 4
    row = report.rows[0]
    assert row.sample_count == 4
    assert row.strike_breach_rate > 0
    assert row.break_even_breach_rate > 0
    assert row.worst_window_drawdown_pct < 0
