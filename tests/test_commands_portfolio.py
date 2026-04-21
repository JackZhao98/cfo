from datetime import datetime, timezone

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
