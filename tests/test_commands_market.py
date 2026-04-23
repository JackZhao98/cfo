from typer.testing import CliRunner

from cfo.cli import app
from cfo.core.wheel_risk import WheelCandidate, WheelRiskReport

runner = CliRunner()


def test_market_wheel_risk_plain(monkeypatch):
    def fake_analyze_symbol(symbol, **kwargs):
        assert symbol == "SOFI"
        return WheelRiskReport(
            symbol="SOFI",
            spot_price=18.97,
            selected_expiration="2026-05-22",
            dte=30,
            stock_risk_score=58.4,
            stock_risk_label="medium",
            summary="medium risk (58.4/100); next earnings lands before expiration",
            current_iv=0.71,
            hv20=0.48,
            hv60=0.41,
            iv_hv20_ratio=1.48,
            iv_rank_90d=77.2,
            next_earnings_date="2026-04-29",
            days_to_earnings=7,
            earnings_before_expiration=True,
            avg_earnings_gap_pct=7.4,
            max_earnings_gap_pct=11.2,
            news_sentiment=-0.12,
            news_risk=51.0,
            news_heat_72h=4,
            vix=27.5,
            components={
                "realized_vol_risk": 49.1,
                "trend_risk": 55.2,
                "earnings_risk": 74.0,
                "news_risk": 51.0,
                "iv_regime_risk": 66.0,
                "market_regime_risk": 60.0,
            },
            top_candidates=[
                WheelCandidate(
                    strike=16.0,
                    premium=0.385,
                    bid=0.34,
                    ask=0.43,
                    mark=0.385,
                    delta=-0.168,
                    iv=0.724,
                    open_interest=1255,
                    volume=162,
                    break_even=15.615,
                    otm_pct=15.66,
                    break_even_buffer_pct=17.68,
                    annualized_yield_pct=29.27,
                    assignment_prob=16.8,
                    spread_pct=23.38,
                    liquidity_risk=22.0,
                    assignment_risk=16.8,
                    candidate_risk=39.8,
                    wheel_fit_score=64.5,
                    notes=["spans earnings"],
                )
            ],
        )

    monkeypatch.setattr("cfo.commands.market.core_wheel_risk.analyze_symbol", fake_analyze_symbol)
    result = runner.invoke(app, ["market", "wheel-risk", "SOFI", "--format", "plain"])
    assert result.exit_code == 0, result.stdout
    assert "stock_risk_score: 58.4" in result.stdout
    assert "selected_expiration: 2026-05-22" in result.stdout
    assert "top_candidates:" in result.stdout


def test_market_wheel_risk_table(monkeypatch):
    def fake_analyze_symbol(symbol, **kwargs):
        return WheelRiskReport(
            symbol=symbol,
            spot_price=18.97,
            selected_expiration="2026-05-22",
            dte=30,
            stock_risk_score=58.4,
            stock_risk_label="medium",
            summary="medium risk",
            current_iv=0.71,
            hv20=0.48,
            hv60=0.41,
            iv_hv20_ratio=1.48,
            iv_rank_90d=77.2,
            next_earnings_date="2026-04-29",
            days_to_earnings=7,
            earnings_before_expiration=True,
            avg_earnings_gap_pct=7.4,
            max_earnings_gap_pct=11.2,
            news_sentiment=-0.12,
            news_risk=51.0,
            news_heat_72h=4,
            vix=27.5,
            components={"earnings_risk": 74.0},
            top_candidates=[],
        )

    monkeypatch.setattr("cfo.commands.market.core_wheel_risk.analyze_symbol", fake_analyze_symbol)
    result = runner.invoke(app, ["market", "wheel-risk", "SOFI"])
    assert result.exit_code == 0, result.stdout
    assert "Wheel Risk" in result.stdout
    assert "Risk Components" in result.stdout
