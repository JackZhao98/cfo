from datetime import datetime, timezone
from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import tradebook as core
from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource

runner = CliRunner()


def test_tradebook_add_paper_stock(tmp_data_dir):
    result = runner.invoke(app, [
        "tradebook", "add",
        "--paper", "--account", "paper/wheel-sofi-2k",
        "--symbol", "SOFI", "--side", "buy",
        "--qty", "10", "--price", "8.0", "--total", "80.0",
        "--strategy", "wheel-sofi",
    ])
    assert result.exit_code == 0, result.stdout
    trades = core.load_all()
    assert len(trades) == 1
    t = trades[0]
    assert t.mode == TradeMode.paper
    assert t.symbol == "SOFI"
    assert t.qty == 10


def test_tradebook_show_filters(tmp_data_dir):
    # Seed a few
    for sym in ("VOO", "NVDA", "SOFI"):
        runner.invoke(app, [
            "tradebook", "add", "--paper",
            "--account", "paper/x", "--symbol", sym,
            "--side", "buy", "--qty", "1", "--price", "10", "--total", "10",
        ])
    result = runner.invoke(app, ["tradebook", "show", "--symbol", "NVDA"])
    assert result.exit_code == 0
    assert "NVDA" in result.stdout
    assert "VOO" not in result.stdout


def test_tradebook_show_empty(tmp_data_dir):
    result = runner.invoke(app, ["tradebook", "show"])
    assert result.exit_code == 0
    assert "no trades" in result.stdout.lower()
