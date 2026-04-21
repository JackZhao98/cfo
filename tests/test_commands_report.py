"""Tests for cfo report command."""
from datetime import date, datetime, timezone

from typer.testing import CliRunner

from cfo.cli import app
from cfo.core import portfolio as core_p
from cfo.core import tradebook as core_tb
from cfo.schemas.portfolio import Account, AccountsFile, AccountSource, AccountType
from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource
from cfo.util import audit, paths, timerange

runner = CliRunner()


def _seed(tmp_data_dir):
    core_p.save(AccountsFile(
        schema_version=1, last_updated=datetime.now(timezone.utc),
        accounts=[Account(
            id="rh-individual", type=AccountType.taxable, broker="robinhood",
            source=AccountSource.rh_sync, balance=30000,
        )],
    ))
    core_tb.append(Trade(
        id="t1", ts=datetime.now(timezone.utc),
        mode=TradeMode.real, account_id="rh-individual", source=TradeSource.rh,
        symbol="VOO", side=TradeSide.buy, qty=0.5, price=400, total=200, strategy="dca-voo",
    ))
    audit.record(cmd=["cfo", "portfolio", "show"], result="ok", duration_ms=1)


def test_report_weekly_writes_markdown(tmp_data_dir):
    _seed(tmp_data_dir)
    r = runner.invoke(app, ["report", "weekly"])
    assert r.exit_code == 0, r.stdout
    week_id = timerange.iso_week_id(date.today())
    out = paths.reports_dir() / f"{week_id}-weekly.md"
    assert out.exists()
    md = out.read_text()
    assert "# Weekly Report" in md


def test_report_monthly_writes_markdown(tmp_data_dir):
    _seed(tmp_data_dir)
    r = runner.invoke(app, ["report", "monthly"])
    assert r.exit_code == 0, r.stdout
    month = timerange.month_id(date.today())
    out = paths.reports_dir() / f"{month}-monthly.md"
    assert out.exists()


def test_report_monthly_creates_history_snapshot(tmp_data_dir):
    _seed(tmp_data_dir)
    r = runner.invoke(app, ["report", "monthly"])
    assert r.exit_code == 0, r.stdout
    month = timerange.month_id(date.today())
    snap = paths.portfolio_history_dir() / f"{month}.json"
    assert snap.exists()


def test_report_audit_summary(tmp_data_dir):
    _seed(tmp_data_dir)
    audit.record(cmd=["cfo", "tradebook", "add"], result="error", duration_ms=2)
    today = date.today().isoformat()
    r = runner.invoke(app, ["report", "audit", "--since", today, "--until", today])
    assert r.exit_code == 0
    assert "ok" in r.stdout.lower()
    assert "error" in r.stdout.lower()


def test_report_audit_empty_range(tmp_data_dir):
    r = runner.invoke(app, [
        "report", "audit",
        "--since", "2020-01-01", "--until", "2020-01-31",
    ])
    assert r.exit_code == 0
    assert "no audit" in r.stdout.lower() or "0" in r.stdout


def test_report_audit_invalid_date(tmp_data_dir):
    r = runner.invoke(app, [
        "report", "audit",
        "--since", "not-a-date", "--until", "2020-01-31",
    ])
    assert r.exit_code == 1
