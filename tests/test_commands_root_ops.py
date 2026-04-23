import json as _json
import subprocess
from datetime import datetime, timezone

from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import paper as core_paper
from cfo.core import portfolio as core_portfolio
from cfo.core import strategy as core_strategy
from cfo.core import tradebook as core_tradebook
from cfo.schemas.paper import PaperKind
from cfo.schemas.portfolio import Account, AccountSource, AccountType, AccountsFile
from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource

runner = CliRunner()


def test_sync_runs_full_default_flow(tmp_data_dir, monkeypatch):
    rh_log = tmp_data_dir["rh_config"] / "trades.jsonl"
    rh_log.write_text(
        '{"ts":"2026-04-21T05:37:41Z","rh_order_id":"oid1","account_number":"597357623","symbol":"QQQM","side":"buy","type":"MKT","tif":"GFD","shares":"0.037424","price":"267.2100","notional_usd":"10.00","state":"queued"}\n',
        encoding="utf-8",
    )
    snapshot_payload = {
        "accounts": [
            {
                "account_number": "597357623",
                "brokerage_account_type": "individual",
                "portfolio_value": 31000,
                "cash": 50,
                "holdings": [],
            },
        ],
    }
    order_payload = {
        "id": "oid1",
        "state": "queued",
        "updated_at": "2026-04-21T05:37:41Z",
        "cumulative_quantity": 0,
        "average_price": 0,
    }

    class Fake:
        def __init__(self, stdout):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(cmd, *args, **kwargs):
        if cmd[:3] == ["rh", "account", "snapshot"]:
            return Fake(_json.dumps(snapshot_payload))
        if cmd[:2] == ["rh", "activity"]:
            return Fake(_json.dumps({"count": 0, "orders": []}))
        if cmd[:2] == ["rh", "order"]:
            return Fake(_json.dumps(order_payload))
        raise AssertionError(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = runner.invoke(app, ["sync"])
    assert r.exit_code == 0, r.stdout
    assert "1 imported trades" in r.stdout
    assert "1 refreshed" in r.stdout
    trades = core_tradebook.load_all()
    assert len(trades) == 1
    assert trades[0].symbol == "QQQM"


def test_status_prints_unified_overview(tmp_data_dir):
    core_portfolio.save(AccountsFile(
        schema_version=1,
        last_updated=datetime.now(timezone.utc),
        accounts=[
            Account(
                id="rh-roth",
                type=AccountType.roth_ira,
                broker="robinhood",
                source=AccountSource.rh_sync,
                balance=8915.57,
            ),
        ],
    ))
    core_strategy.new_strategy("wheel", template="wheel")
    core_paper.create(kind=PaperKind.strategy, pid="wheel-sofi-2k", capital=2000, strategy_ref="wheel")
    core_strategy.set_live_account("wheel", "rh-roth")
    core_strategy.set_capital_budget("wheel", 2000)
    core_tradebook.append(Trade(
        id="t1", ts=datetime.now(timezone.utc),
        mode=TradeMode.real, account_id="rh-roth", source=TradeSource.rh,
        symbol="QQQM", side=TradeSide.buy, qty=0.1, total=10,
        rh_order_id="oid1", order_state="queued", strategy="wheel",
    ))

    r = runner.invoke(app, ["status", "--trades-limit", "3", "--pending-limit", "3"])
    assert r.exit_code == 0, r.stdout
    assert "Net Worth Snapshot" in r.stdout
    assert "Accounts" in r.stdout
    assert "Strategies" in r.stdout
    assert "Pending Orders" in r.stdout
    assert "Recent Trades" in r.stdout
    assert "wheel" in r.stdout
    assert "QQQM" in r.stdout


def test_status_plain_and_json(tmp_data_dir):
    core_portfolio.save(AccountsFile(
        schema_version=1,
        last_updated=datetime.now(timezone.utc),
        accounts=[
            Account(
                id="rh-roth",
                type=AccountType.roth_ira,
                broker="robinhood",
                source=AccountSource.rh_sync,
                balance=8915.57,
            ),
        ],
    ))
    core_strategy.new_strategy("wheel", template="wheel")

    plain = runner.invoke(app, ["status", "--format", "plain"])
    assert plain.exit_code == 0, plain.stdout
    assert "summary:" in plain.stdout
    assert "accounts:" in plain.stdout
    assert "strategies:" in plain.stdout

    raw = runner.invoke(app, ["status", "--format", "json"])
    assert raw.exit_code == 0, raw.stdout
    payload = _json.loads(raw.stdout)
    assert payload["summary"]["account_count"] == 1
    assert payload["strategies"][0]["name"] == "wheel"
