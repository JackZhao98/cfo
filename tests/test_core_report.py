from datetime import date, datetime, timezone

from cfo.core import report
from cfo.core import portfolio as core_p
from cfo.core import tradebook as core_tb
from cfo.core import strategy as core_s
from cfo.schemas.portfolio import Account, AccountsFile, AccountSource, AccountType
from cfo.schemas.strategy import StrategyState
from cfo.schemas.tradebook import Trade, TradeMode, TradeSide, TradeSource
from cfo.util import audit


def _seed_tradebook(day: date):
    ts = datetime(day.year, day.month, day.day, 9, 30, tzinfo=timezone.utc)
    core_tb.append(Trade(
        id="t1", ts=ts, mode=TradeMode.real,
        account_id="rh-individual", source=TradeSource.rh,
        symbol="VOO", side=TradeSide.buy, qty=0.5, price=400, total=200, strategy="dca-voo",
    ))
    core_tb.append(Trade(
        id="t2", ts=ts, mode=TradeMode.paper,
        account_id="paper/x", source=TradeSource.cfo,
        symbol="SOFI", side=TradeSide.sell_put, qty=1, strike=8, premium=0.35, total=35,
        strategy="wheel-sofi",
    ))


def test_weekly_includes_section_headers(tmp_data_dir):
    _seed_tradebook(date.today())
    audit.record(cmd=["cfo", "portfolio", "show"], result="ok", duration_ms=1)
    md = report.weekly(today=date.today())
    # Key sections
    for header in ("# Weekly Report", "## Trades", "## Strategies",
                   "## Portfolio", "## Audit", "## Price Log"):
        assert header in md


def test_weekly_counts_trades_in_range(tmp_data_dir):
    today = date.today()
    _seed_tradebook(today)
    md = report.weekly(today=today)
    # Both trades should appear (both today, which is always in this week)
    assert "VOO" in md
    assert "SOFI" in md


def test_weekly_empty(tmp_data_dir):
    md = report.weekly(today=date.today())
    assert "No trades" in md or "0 trade" in md


def test_monthly_structure(tmp_data_dir):
    _seed_tradebook(date.today())
    md = report.monthly(today=date.today())
    assert "# Monthly Report" in md
    assert "## Portfolio" in md


def test_weekly_snapshot_delta_when_prev_exists(tmp_data_dir):
    from cfo.core import history
    core_p.save(AccountsFile(
        schema_version=1, last_updated=datetime.now(timezone.utc),
        accounts=[Account(
            id="a", type=AccountType.taxable, broker="x",
            source=AccountSource.manual, balance=100.0,
        )],
    ))
    history.snapshot_current(label="2026-W16")
    # bump then report
    core_p.update_balance("a", 150.0)
    md = report.weekly(today=date(2026, 4, 22))  # W17
    # Should include portfolio delta vs W16 (+50.00)
    assert "50" in md
