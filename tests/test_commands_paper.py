from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import paper as core

runner = CliRunner()


def test_paper_create_strategy(tmp_data_dir):
    r = runner.invoke(app, [
        "paper", "create",
        "--type", "strategy", "--name", "wheel-sofi-2k",
        "--strategy", "wheel-sofi", "--capital", "2000",
    ])
    assert r.exit_code == 0, r.stdout
    m = core.load_meta("wheel-sofi-2k")
    assert m.capital_start == 2000


def test_paper_list(tmp_data_dir):
    runner.invoke(app, ["paper", "create", "--type", "strategy", "--name", "a",
                        "--strategy", "x", "--capital", "100"])
    r = runner.invoke(app, ["paper", "list"])
    assert r.exit_code == 0
    assert "a" in r.stdout


def test_paper_close(tmp_data_dir):
    runner.invoke(app, ["paper", "create", "--type", "composite",
                        "--name", "sim", "--capital", "1000"])
    r = runner.invoke(app, ["paper", "close", "sim"])
    assert r.exit_code == 0
    m = core.load_meta("sim")
    assert m.status == "closed"
