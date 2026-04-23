from typer.testing import CliRunner
import json

from cfo.cli import app
from cfo.core import paper as core
from cfo.core import strategy as strategy_core

runner = CliRunner()


def test_paper_create_strategy(tmp_data_dir):
    strategy_core.new_strategy(name="wheel-sofi", template="wheel")
    r = runner.invoke(app, [
        "paper", "create",
        "--type", "strategy", "--name", "wheel-sofi-2k",
        "--strategy", "wheel-sofi", "--capital", "2000",
    ])
    assert r.exit_code == 0, r.stdout
    m = core.load_meta("wheel-sofi-2k")
    assert m.capital_start == 2000
    assert strategy_core.load_meta("wheel-sofi").paper_portfolio == "wheel-sofi-2k"


def test_paper_list(tmp_data_dir):
    strategy_core.new_strategy(name="x", template="wheel")
    runner.invoke(app, ["paper", "create", "--type", "strategy", "--name", "a",
                        "--strategy", "x", "--capital", "100"])
    r = runner.invoke(app, ["paper", "list"])
    assert r.exit_code == 0
    assert "a" in r.stdout


def test_paper_list_json(tmp_data_dir):
    strategy_core.new_strategy(name="x", template="wheel")
    runner.invoke(app, ["paper", "create", "--type", "strategy", "--name", "a",
                        "--strategy", "x", "--capital", "100"])
    r = runner.invoke(app, ["paper", "list", "--format", "json"])
    assert r.exit_code == 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["count"] == 1
    assert payload["paper_portfolios"][0]["id"] == "a"


def test_paper_close(tmp_data_dir):
    runner.invoke(app, ["paper", "create", "--type", "composite",
                        "--name", "sim", "--capital", "1000"])
    r = runner.invoke(app, ["paper", "close", "sim"])
    assert r.exit_code == 0
    m = core.load_meta("sim")
    assert m.status == "closed"


def test_paper_create_strategy_rejects_missing_strategy(tmp_data_dir):
    r = runner.invoke(app, [
        "paper", "create",
        "--type", "strategy", "--name", "a",
        "--strategy", "missing", "--capital", "100",
    ])
    assert r.exit_code != 0
    assert "strategy not found" in r.stdout.lower()


def test_paper_create_strategy_rejects_second_binding(tmp_data_dir):
    strategy_core.new_strategy(name="x", template="wheel")
    r1 = runner.invoke(app, [
        "paper", "create",
        "--type", "strategy", "--name", "a",
        "--strategy", "x", "--capital", "100",
    ])
    assert r1.exit_code == 0
    r2 = runner.invoke(app, [
        "paper", "create",
        "--type", "strategy", "--name", "b",
        "--strategy", "x", "--capital", "100",
    ])
    assert r2.exit_code != 0
    assert "already bound to paper portfolio" in r2.stdout.lower()


def test_paper_close_strategy_clears_binding(tmp_data_dir):
    strategy_core.new_strategy(name="x", template="wheel")
    runner.invoke(app, [
        "paper", "create",
        "--type", "strategy", "--name", "a",
        "--strategy", "x", "--capital", "100",
    ])
    r = runner.invoke(app, ["paper", "close", "a"])
    assert r.exit_code == 0
    assert strategy_core.load_meta("x").paper_portfolio is None
