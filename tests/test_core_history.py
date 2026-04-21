import json
from datetime import date, datetime, timezone

from cfo.core import history
from cfo.core import portfolio as core_p
from cfo.schemas.portfolio import Account, AccountsFile, AccountSource, AccountType
from cfo.util import paths


def _seed():
    core_p.save(
        AccountsFile(
            schema_version=1,
            last_updated=datetime.now(timezone.utc),
            accounts=[
                Account(
                    id="rh-individual", type=AccountType.taxable, broker="robinhood",
                    source=AccountSource.rh_sync, balance=30000, cash=500,
                ),
                Account(
                    id="chase", type=AccountType.checking, broker="chase",
                    source=AccountSource.manual, balance=12979.47,
                ),
            ],
        )
    )


def test_snapshot_current(tmp_data_dir):
    _seed()
    path = history.snapshot_current(label="2026-04")
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["label"] == "2026-04"
    assert data["total"] == 30000 + 12979.47
    assert len(data["accounts"]) == 2


def test_load_returns_none_when_missing(tmp_data_dir):
    assert history.load("2026-04") is None


def test_load_returns_data_when_exists(tmp_data_dir):
    _seed()
    history.snapshot_current(label="2026-04")
    data = history.load("2026-04")
    assert data is not None
    assert data["label"] == "2026-04"


def test_total_delta(tmp_data_dir):
    _seed()
    history.snapshot_current(label="2026-03")
    # Bump balance then snap again
    core_p.update_balance(account_id="chase", balance=13500)
    history.snapshot_current(label="2026-04")
    delta = history.total_delta(prev_label="2026-03", curr_label="2026-04")
    assert round(delta, 2) == round(13500 - 12979.47, 2)


def test_total_delta_missing(tmp_data_dir):
    assert history.total_delta(prev_label="x", curr_label="y") is None
