from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import strategy as core

runner = CliRunner()


def test_strategy_new_and_list(tmp_data_dir):
    r = runner.invoke(app, ["strategy", "new", "wheel-sofi", "--template", "wheel"])
    assert r.exit_code == 0
    r2 = runner.invoke(app, ["strategy", "list"])
    assert r2.exit_code == 0
    assert "wheel-sofi" in r2.stdout
    assert "draft" in r2.stdout


def test_strategy_status_transition(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    r = runner.invoke(app, ["strategy", "status", "x", "--to", "observing"])
    assert r.exit_code == 0
    assert core.load_meta("x").state.value == "observing"


def test_strategy_status_illegal(tmp_data_dir):
    runner.invoke(app, ["strategy", "new", "x", "--template", "blank"])
    r = runner.invoke(app, ["strategy", "status", "x", "--to", "live"])
    assert r.exit_code != 0
    assert "illegal" in r.stdout.lower() or "illegal" in str(r.exception).lower()
