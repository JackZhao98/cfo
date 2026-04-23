from datetime import datetime, timezone
import json

from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import portfolio as core
from cfo.schemas.portfolio import Account, AccountsFile, AccountType, AccountSource

runner = CliRunner()


def _seed(tmp_data_dir):
    core.save(AccountsFile(
        schema_version=1,
        last_updated=datetime.now(timezone.utc),
        accounts=[
            Account(
                id="chase",
                type=AccountType.checking,
                broker="chase",
                source=AccountSource.manual,
                balance=12979.47,
            ),
            Account(
                id="rh-individual",
                type=AccountType.taxable,
                broker="robinhood",
                source=AccountSource.rh_sync,
                balance=30000.00,
            ),
        ],
    ))


def test_portfolio_show_empty(tmp_data_dir):
    result = runner.invoke(app, ["portfolio", "show"])
    assert result.exit_code == 0
    assert "no accounts" in result.stdout.lower()


def test_portfolio_show_populated(tmp_data_dir):
    _seed(tmp_data_dir)
    result = runner.invoke(app, ["portfolio", "show"])
    assert result.exit_code == 0
    assert "chase" in result.stdout
    assert "12979.47" in result.stdout or "12,979.47" in result.stdout
    assert "rh-individual" in result.stdout


def test_portfolio_show_plain_and_json(tmp_data_dir):
    _seed(tmp_data_dir)
    plain = runner.invoke(app, ["portfolio", "show", "--format", "plain"])
    assert plain.exit_code == 0, plain.stdout
    assert "accounts:" in plain.stdout
    assert "id: chase" in plain.stdout

    raw = runner.invoke(app, ["portfolio", "show", "--format", "json"])
    assert raw.exit_code == 0, raw.stdout
    payload = json.loads(raw.stdout)
    assert payload["count"] == 2
    assert payload["accounts"][0]["id"] == "chase"


def test_portfolio_update_balance(tmp_data_dir):
    _seed(tmp_data_dir)
    result = runner.invoke(app, ["portfolio", "update", "--account", "chase", "--balance", "13500"])
    assert result.exit_code == 0
    loaded = core.load()
    a = [x for x in loaded.accounts if x.id == "chase"][0]
    assert a.balance == 13500


def test_portfolio_update_unknown_account_exits_nonzero(tmp_data_dir):
    _seed(tmp_data_dir)
    result = runner.invoke(app, ["portfolio", "update", "--account", "nope", "--balance", "1"])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower() or "not found" in str(result.exception).lower()


def test_portfolio_add_manual_account(tmp_data_dir):
    result = runner.invoke(app, [
        "portfolio", "add",
        "--account", "chase",
        "--type", "checking",
        "--broker", "chase",
        "--balance", "12979.47",
    ])
    assert result.exit_code == 0, result.stdout
    loaded = core.load()
    a = [x for x in loaded.accounts if x.id == "chase"][0]
    assert a.balance == 12979.47
    assert a.source == AccountSource.manual
    assert a.cash == 12979.47


def test_portfolio_add_duplicate_rejected(tmp_data_dir):
    _seed(tmp_data_dir)
    result = runner.invoke(app, [
        "portfolio", "add",
        "--account", "chase",
        "--type", "checking",
        "--broker", "chase",
        "--balance", "1",
    ])
    assert result.exit_code != 0
    assert "already exists" in result.stdout.lower()


def test_sync_upserts_accounts(tmp_data_dir, monkeypatch):
    import subprocess
    import json as _json

    # Real rh `account snapshot --format json` shape
    payload = {
        "total_portfolio": 16956.93,
        "total_cash": 11383.71,
        "accounts": [
            {
                "account_number": "597357623",
                "brokerage_account_type": "individual",
                "account_type": "margin",
                "nickname": "Trading",
                "portfolio_value": 8043.00,
                "cash": 7450.38,
                "buying_power": 7400.38,
                "holdings": [
                    {"symbol": "TSLA", "shares": 1.508102, "avg_cost": 416.89,
                     "current_price": 392.4, "total_return": -36.93, "total_equity": 591.78},
                ],
            },
            {
                "account_number": "647360304",
                "brokerage_account_type": "ira_roth",
                "account_type": "cash",
                "portfolio_value": 8913.93,
                "cash": 3933.33,
                "buying_power": 3442.83,
                "holdings": [
                    {"symbol": "VOO", "shares": 5.005019, "avg_cost": 610.56,
                     "current_price": 652.23, "total_return": 208.56, "total_equity": 3264.42},
                ],
            },
        ],
    }

    class Fake:
        returncode = 0
        stdout = _json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())

    result = runner.invoke(app, ["portfolio", "sync"])
    assert result.exit_code == 0, result.stdout

    from cfo.core import portfolio as core
    af = core.load()
    by_id = {a.id: a for a in af.accounts}
    assert "rh-individual" in by_id
    assert "rh-roth" in by_id
    # Verify field mapping worked
    ind = by_id["rh-individual"]
    assert ind.balance == 8043.00
    assert ind.cash == 7450.38
    assert ind.type == AccountType.taxable
    assert len(ind.holdings) == 1
    assert ind.holdings[0].symbol == "TSLA"
    assert ind.holdings[0].qty == 1.508102
    assert ind.holdings[0].cost_basis == 416.89
    roth = by_id["rh-roth"]
    assert roth.type == AccountType.roth_ira
    assert roth.holdings[0].symbol == "VOO"


def test_sync_unknown_account_type_falls_back_to_account_number(tmp_data_dir, monkeypatch):
    import subprocess
    import json as _json

    payload = {
        "accounts": [
            {
                "account_number": "999",
                "brokerage_account_type": "some_weird_type",
                "portfolio_value": 1000,
                "cash": 100,
                "holdings": [],
            },
        ],
    }

    class Fake:
        returncode = 0
        stdout = _json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    result = runner.invoke(app, ["portfolio", "sync"])
    assert result.exit_code == 0, result.stdout

    af = core.load()
    ids = {a.id for a in af.accounts}
    assert "rh-999" in ids
    acc = [a for a in af.accounts if a.id == "rh-999"][0]
    assert acc.type == AccountType.other


def test_sync_managed_individual_gets_distinct_id(tmp_data_dir, monkeypatch):
    import subprocess
    import json as _json

    payload = {
        "accounts": [
            {
                "account_number": "597357623",
                "brokerage_account_type": "individual",
                "management_type": "self_directed",
                "portfolio_value": 8043.00,
                "cash": 7450.38,
                "holdings": [],
            },
            {
                "account_number": "181785371244",
                "brokerage_account_type": "individual",
                "management_type": "managed",
                "portfolio_value": 1507.58,
                "cash": 7.65,
                "holdings": [],
            },
        ],
    }

    class Fake:
        returncode = 0
        stdout = _json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    result = runner.invoke(app, ["portfolio", "sync"])
    assert result.exit_code == 0, result.stdout

    af = core.load()
    ids = {a.id for a in af.accounts}
    assert "rh-individual" in ids
    assert "rh-managed-individual" in ids


def test_sync_rh_failure_exits_nonzero(tmp_data_dir, monkeypatch):
    import subprocess

    class Fake:
        returncode = 1
        stdout = ""
        stderr = "not authenticated"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    result = runner.invoke(app, ["portfolio", "sync"])
    assert result.exit_code != 0


def test_sync_preserves_non_rh_accounts(tmp_data_dir, monkeypatch):
    _seed(tmp_data_dir)
    import subprocess
    import json as _json

    payload = {
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

    class Fake:
        returncode = 0
        stdout = _json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    result = runner.invoke(app, ["portfolio", "sync"])
    assert result.exit_code == 0, result.stdout

    af = core.load()
    ids = {a.id for a in af.accounts}
    assert "chase" in ids  # non-rh preserved
    assert "rh-individual" in ids
    rh = [a for a in af.accounts if a.id == "rh-individual"][0]
    assert rh.balance == 31000


def test_sync_refreshes_pending_order_states(tmp_data_dir, monkeypatch):
    import subprocess
    import json as _json
    from cfo.core import tradebook as tradebook_core
    from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource

    tradebook_core.append(Trade(
        id="x", ts=datetime.now(timezone.utc), mode=TradeMode.real,
        account_id="rh-individual", source=TradeSource.rh,
        symbol="VOO", side=TradeSide.buy, qty=1, rh_order_id="a1", order_state="queued",
    ))

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
        "id": "a1",
        "state": "filled",
        "updated_at": "2026-04-21T04:26:36.896359Z",
        "cumulative_quantity": 1,
        "average_price": 100.5,
    }

    class Fake:
        def __init__(self, stdout):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(cmd, *args, **kwargs):
        if cmd[:3] == ["rh", "account", "snapshot"]:
            return Fake(_json.dumps(snapshot_payload))
        if cmd[:2] == ["rh", "order"]:
            return Fake(_json.dumps(order_payload))
        raise AssertionError(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.invoke(app, ["portfolio", "sync"])
    assert result.exit_code == 0, result.stdout
    updated = tradebook_core.load_all()[0]
    assert updated.order_state == "filled"


def test_sync_imports_missing_rh_trades_from_raw_log(tmp_data_dir, monkeypatch):
    import subprocess
    import json as _json
    from cfo.core import tradebook as tradebook_core

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
        if cmd[:2] == ["rh", "order"]:
            return Fake(_json.dumps(order_payload))
        raise AssertionError(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.invoke(app, ["portfolio", "sync"])
    assert result.exit_code == 0, result.stdout
    trades = tradebook_core.load_all()
    assert len(trades) == 1
    assert trades[0].symbol == "QQQM"
    assert trades[0].rh_order_id == "oid1"
