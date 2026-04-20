from typer.testing import CliRunner

from cfo import __version__
from cfo.cli import app

runner = CliRunner()


def test_cli_version_runs():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help_lists_version():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "version" in result.stdout.lower()
