from typer.testing import CliRunner

from cfo.cli import app
from cfo.core.wheel_risk import WheelBacktestReport, WheelBacktestRow

runner = CliRunner()


def test_market_wheel_backtest_plain(monkeypatch):
    def fake_backtest_symbol(symbol, **kwargs):
        assert symbol == "SOFI"
        return WheelBacktestReport(
            symbol="SOFI",
            lookback_days=252,
            expiration="2026-05-29",
            dte=37,
            evaluation_count=180,
            source_summary="Path-only approximation.",
            current_stock_risk_score=46.1,
            current_stock_risk_label="medium",
            rows=[
                WheelBacktestRow(
                    strike=16.0,
                    break_even=15.52,
                    dte=37,
                    wheel_fit_score=70.5,
                    annualized_yield_pct=29.6,
                    sample_count=180,
                    strike_breach_rate=21.1,
                    break_even_breach_rate=13.3,
                    assigned_rate=12.2,
                    finish_above_break_even_rate=86.7,
                    avg_terminal_return_pct=1.4,
                    worst_window_drawdown_pct=-18.5,
                )
            ],
        )

    monkeypatch.setattr("cfo.commands.market.core_wheel_risk.backtest_symbol", fake_backtest_symbol)
    result = runner.invoke(app, ["market", "wheel-backtest", "SOFI", "--format", "plain"])
    assert result.exit_code == 0, result.stdout
    assert "evaluation_count: 180" in result.stdout
    assert "rows:" in result.stdout


def test_market_wheel_backtest_table(monkeypatch):
    def fake_backtest_symbol(symbol, **kwargs):
        return WheelBacktestReport(
            symbol=symbol,
            lookback_days=252,
            expiration="2026-05-29",
            dte=37,
            evaluation_count=180,
            source_summary="Path-only approximation.",
            current_stock_risk_score=46.1,
            current_stock_risk_label="medium",
            rows=[],
        )

    monkeypatch.setattr("cfo.commands.market.core_wheel_risk.backtest_symbol", fake_backtest_symbol)
    result = runner.invoke(app, ["market", "wheel-backtest", "SOFI"])
    assert result.exit_code == 0, result.stdout
    assert "Wheel Path Backtest" in result.stdout
    assert "Replay Results" in result.stdout
