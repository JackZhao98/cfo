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


def test_reconcile_no_rh_log(tmp_data_dir):
    # no ~/.config/rh/trades.jsonl
    result = runner.invoke(app, ["tradebook", "reconcile"])
    assert result.exit_code == 0
    assert "no rh log" in result.stdout.lower()


def test_reconcile_matches(tmp_data_dir):
    # Write fake rh raw log
    rh_log = tmp_data_dir["rh_config"] / "trades.jsonl"
    rh_log.write_text('{"rh_order_id":"a1","symbol":"VOO","qty":1,"side":"buy","ts":"2026-04-20T09:30:00Z"}\n')
    # Write matching cfo master trade
    from cfo.core import tradebook as core
    from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource
    core.append(Trade(
        id="x", ts=datetime.now(timezone.utc), mode=TradeMode.real,
        account_id="rh-individual", source=TradeSource.rh,
        symbol="VOO", side=TradeSide.buy, qty=1, rh_order_id="a1",
    ))
    result = runner.invoke(app, ["tradebook", "reconcile"])
    assert result.exit_code == 0
    assert "reconciled" in result.stdout.lower() or "ok" in result.stdout.lower()


def test_reconcile_detects_missing_in_cfo(tmp_data_dir):
    rh_log = tmp_data_dir["rh_config"] / "trades.jsonl"
    rh_log.write_text('{"rh_order_id":"a1","symbol":"VOO","qty":1,"side":"buy","ts":"2026-04-20T09:30:00Z"}\n')
    # cfo master has nothing
    result = runner.invoke(app, ["tradebook", "reconcile"])
    assert result.exit_code != 0
    assert "a1" in result.stdout  # flagged
