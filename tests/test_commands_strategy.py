from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import portfolio as portfolio_core
from cfo.core import strategy as core
from cfo.schemas.portfolio import Account, AccountSource, AccountType

runner = CliRunner()


def test_strategy_new_and_list(tmp_data_dir):
    r = runner.invoke(app, ["strategy", "new", "wheel-sofi", "--template", "wheel"])
    assert r.exit_code == 0
    r2 = runner.invoke(app, ["strategy", "list"])
    assert r2.exit_code == 0
    assert "wheel-sofi" in r2.stdout
    assert "draft" in r2.stdout


def test_strategy_list_plain(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "wheel-sofi", "--template", "wheel"])
    r = runner.invoke(app, ["strategy", "list", "--format", "plain"])
    assert r.exit_code == 0, r.stdout
    assert "strategies:" in r.stdout
    assert "name: wheel-sofi" in r.stdout


def test_strategy_status_transition(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    core.set_paper_portfolio("x", "paper-x")
    r = runner.invoke(app, ["strategy", "status", "x", "--to", "observing"])
    assert r.exit_code == 0
    assert core.load_meta("x").state.value == "observing"
    r2 = runner.invoke(app, ["strategy", "status", "x", "--to", "paper"])
    assert r2.exit_code == 0
    assert core.load_meta("x").state.value == "paper"


def test_strategy_status_illegal(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    r = runner.invoke(app, ["strategy", "status", "x", "--to", "live"])
    assert r.exit_code != 0
    assert "illegal" in r.stdout.lower() or "illegal" in str(r.exception).lower()


def test_strategy_bind_live(tmp_data_dir):
    portfolio_core.add_account(Account(
        id="rh-roth",
        type=AccountType.roth_ira,
        broker="robinhood",
        source=AccountSource.rh_sync,
        balance=1000,
    ))
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    r = runner.invoke(app, ["strategy", "bind-live", "x", "--account", "rh-roth"])
    assert r.exit_code == 0
    assert core.load_meta("x").live_account == "rh-roth"


def test_strategy_bind_live_rejects_missing_account(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    r = runner.invoke(app, ["strategy", "bind-live", "x", "--account", "missing"])
    assert r.exit_code != 0
    assert "account not found" in r.stdout.lower()


def test_strategy_clear_live(tmp_data_dir):
    portfolio_core.add_account(Account(
        id="rh-individual",
        type=AccountType.taxable,
        broker="robinhood",
        source=AccountSource.rh_sync,
        balance=1000,
    ))
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    runner.invoke(app, ["strategy", "bind-live", "x", "--account", "rh-individual"])
    r = runner.invoke(app, ["strategy", "clear-live", "x"])
    assert r.exit_code == 0
    assert core.load_meta("x").live_account is None


def test_strategy_set_budget(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    r = runner.invoke(app, ["strategy", "set-budget", "x", "--amount", "2500"])
    assert r.exit_code == 0
    assert core.load_meta("x").capital_budget == 2500


def test_strategy_clear_budget(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    runner.invoke(app, ["strategy", "set-budget", "x", "--amount", "2500"])
    r = runner.invoke(app, ["strategy", "clear-budget", "x"])
    assert r.exit_code == 0
    assert core.load_meta("x").capital_budget is None
