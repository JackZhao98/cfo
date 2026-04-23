import json
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


def test_tradebook_show_plain(tmp_data_dir):
    runner.invoke(app, [
        "tradebook", "add", "--paper",
        "--account", "paper/x", "--symbol", "NVDA",
        "--side", "buy", "--qty", "1", "--price", "10", "--total", "10",
    ])
    result = runner.invoke(app, ["tradebook", "show", "--format", "plain"])
    assert result.exit_code == 0, result.stdout
    assert "trades:" in result.stdout
    assert "symbol: NVDA" in result.stdout


def test_tradebook_show_empty(tmp_data_dir):
    result = runner.invoke(app, ["tradebook", "show"])
    assert result.exit_code == 0
    assert "no trades" in result.stdout.lower()


def test_tradebook_show_skips_malformed_legacy_rows(tmp_data_dir):
    master = tmp_data_dir["data"] / "tradebook" / "master.jsonl"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_text(
        '{"schema_version":1,"id":"legacy","ts":"2026-04-20T09:30:00Z","mode":"real","account_id":"rh-individual","source":"legacy_csv","symbol":"VOO","side":"","qty":null}\n'
        '{"schema_version":1,"id":"ok","ts":"2026-04-20T09:31:00Z","mode":"paper","account_id":"paper/x","source":"cfo","symbol":"SOFI","side":"buy","qty":1,"price":10,"total":10}\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["tradebook", "show"])
    assert result.exit_code == 0, result.stdout
    assert "SOFI" in result.stdout


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


def test_tradebook_repair_rebuilds_from_legacy_csv(tmp_data_dir, tmp_path):
    src = tmp_path / "trades.csv"
    src.write_text(
        "Date,Time,Acct,Symbol,Side,Qty,Price,Type,TIF,Strike,Expiry,CP,Notional,Effect,Status,Mode,OrderID,Notes\n"
        "2026-04-20,10:00:00,Roth,SOFI,STO,1,0.73,LMT,GTC,17.50,2026-05-22,P,73.00,CR,OPEN,PAPER,,Wheel #1 paper\n"
        "2026-04-20,16:44:25,Trading,VOO,BTO,0.07663,652.43,MKT,GFD,,,,50.00,DR,QUEUED,REAL,abc123,Layer 3 test\n",
        encoding="utf-8",
    )
    master = tmp_data_dir["data"] / "tradebook" / "master.jsonl"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_text('{"bad": true}\n', encoding="utf-8")
    result = runner.invoke(app, ["tradebook", "repair", "--src", str(src)])
    assert result.exit_code == 0, result.stdout
    repaired = core.load_all()
    assert len(repaired) == 2
    assert repaired[0].symbol == "SOFI"
    assert repaired[1].symbol == "VOO"
    assert repaired[1].order_state == "queued"


def test_tradebook_sync_orders_updates_state(tmp_data_dir, monkeypatch):
    import subprocess
    core.append(Trade(
        id="x", ts=datetime.now(timezone.utc), mode=TradeMode.real,
        account_id="rh-individual", source=TradeSource.rh,
        symbol="VOO", side=TradeSide.buy, qty=1, rh_order_id="a1", order_state="queued",
    ))

    payload = {
        "id": "a1",
        "state": "filled",
        "updated_at": "2026-04-21T04:26:36.896359Z",
        "cumulative_quantity": 1,
        "average_price": 100.5,
    }

    class Fake:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    result = runner.invoke(app, ["tradebook", "sync-orders"])
    assert result.exit_code == 0, result.stdout
    updated = core.load_all()[0]
    assert updated.order_state == "filled"
    assert updated.fill_price == 100.5


def test_tradebook_import_rh_imports_missing_real_orders(tmp_data_dir):
    rh_log = tmp_data_dir["rh_config"] / "trades.jsonl"
    rh_log.write_text(
        '{"ts":"2026-04-21T05:37:41Z","rh_order_id":"oid1","account_number":"597357623","symbol":"QQQM","side":"buy","type":"MKT","tif":"GFD","shares":"0.037424","price":"267.2100","notional_usd":"10.00","state":"queued"}\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["tradebook", "import-rh"])
    assert result.exit_code == 0, result.stdout
    trades = core.load_all()
    assert len(trades) == 1
    assert trades[0].symbol == "QQQM"
    assert trades[0].rh_order_id == "oid1"
