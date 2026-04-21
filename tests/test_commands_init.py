from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import portfolio as core_p
from cfo.core import profile as core_prof

runner = CliRunner()


def _responses(**overrides):
    """Default responses in order matching init prompts."""
    base = {
        "name": "Jack",
        "age": "28",
        "occupation": "Software Engineer, $180k",
        "family_backup": "y",
        "monthly_expenses": "3000",
        "has_rh": "y",
        "rh_individual": "30000",
        "rh_roth": "14500",
        "rh_traditional": "0",
        "rh_savings": "25331.84",
        "external": "chase|checking|12979.47",
        "max_drawdown": "30",
        "horizon": "20",
        "primary_goal": "retirement",
        "monthly_invest": "1000",
        "paper_done": "y",
        "options_done": "y",
        "advisors": "tiange",
        "philosophy": "long-term compounding with tactical options",
    }
    base.update(overrides)
    return "\n".join(base.values()) + "\n"


def test_init_creates_profile_and_accounts(tmp_data_dir):
    result = runner.invoke(app, ["init"], input=_responses())
    assert result.exit_code == 0, result.stdout

    profile = core_prof.load()
    assert profile is not None
    assert "Jack" in profile
    assert "Software Engineer" in profile

    af = core_p.load()
    ids = {a.id for a in af.accounts}
    assert "rh-individual" in ids
    assert "rh-roth" in ids
    assert "rh-savings" in ids
    assert "chase" in ids
    # rh-traditional=0 是否记录 — 设计决定:balance 0 也记,用户可能以后要用
    assert "rh-traditional" in ids


def test_init_skips_rh_when_no(tmp_data_dir):
    result = runner.invoke(app, ["init"], input=_responses(
        has_rh="n",
        rh_individual="",
        rh_roth="",
        rh_traditional="",
        rh_savings="",
    ))
    assert result.exit_code == 0
    af = core_p.load()
    ids = {a.id for a in af.accounts}
    assert not any(i.startswith("rh-") for i in ids)


def test_init_refuses_to_overwrite_existing(tmp_data_dir):
    # First run
    runner.invoke(app, ["init"], input=_responses())
    # Second run should refuse
    result = runner.invoke(app, ["init"], input=_responses())
    assert result.exit_code != 0
    assert "already" in result.stdout.lower() or "exists" in result.stdout.lower()
