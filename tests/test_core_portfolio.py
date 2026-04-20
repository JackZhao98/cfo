from datetime import datetime, timezone

import pytest

from cfo.core import portfolio as core
from cfo.schemas.portfolio import Account, AccountsFile, AccountType, AccountSource
from cfo.util import paths


def _sample_file() -> AccountsFile:
    return AccountsFile(
        schema_version=1,
        last_updated=datetime.now(timezone.utc),
        accounts=[
            Account(
                id="chase",
                type=AccountType.checking,
                broker="chase",
                source=AccountSource.manual,
                balance=100.00,
            )
        ],
    )


def test_save_and_load_roundtrip(tmp_data_dir):
    af = _sample_file()
    core.save(af)
    loaded = core.load()
    assert len(loaded.accounts) == 1
    assert loaded.accounts[0].id == "chase"


def test_load_missing_returns_empty(tmp_data_dir):
    af = core.load()
    assert af.schema_version == 1
    assert af.accounts == []


def test_update_balance_existing_account(tmp_data_dir):
    core.save(_sample_file())
    core.update_balance(account_id="chase", balance=12979.47)
    loaded = core.load()
    assert loaded.accounts[0].balance == 12979.47
    assert loaded.accounts[0].last_manual_update is not None


def test_update_balance_unknown_account_raises(tmp_data_dir):
    core.save(_sample_file())
    with pytest.raises(KeyError):
        core.update_balance(account_id="nonexistent", balance=100)


def test_add_account(tmp_data_dir):
    core.save(_sample_file())
    core.add_account(Account(
        id="rh-roth",
        type=AccountType.roth_ira,
        broker="robinhood",
        source=AccountSource.rh_sync,
        balance=14500,
    ))
    loaded = core.load()
    ids = [a.id for a in loaded.accounts]
    assert "rh-roth" in ids
    assert len(loaded.accounts) == 2


def test_save_preserves_last_updated(tmp_data_dir):
    explicit_ts = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    af = AccountsFile(
        schema_version=1,
        last_updated=explicit_ts,
        accounts=[
            Account(
                id="chase",
                type=AccountType.checking,
                broker="chase",
                source=AccountSource.manual,
                balance=100.00,
            )
        ],
    )
    core.save(af)
    loaded = core.load()
    assert loaded.last_updated == explicit_ts


def test_add_account_duplicate_id_raises(tmp_data_dir):
    core.save(_sample_file())
    with pytest.raises(ValueError):
        core.add_account(Account(
            id="chase",
            type=AccountType.checking,
            broker="chase",
            source=AccountSource.manual,
            balance=500,
        ))
