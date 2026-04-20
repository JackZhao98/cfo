import pytest
from pydantic import ValidationError

from cfo.schemas.portfolio import Account, Holding, AccountsFile, AccountType, AccountSource


def test_holding_valid():
    h = Holding(symbol="VOO", qty=10.0, cost_basis=5000.0)
    assert h.symbol == "VOO"


def test_holding_negative_qty_rejected():
    with pytest.raises(ValidationError):
        Holding(symbol="VOO", qty=-1, cost_basis=100)


def test_account_minimum():
    a = Account(
        id="rh-individual",
        type=AccountType.taxable,
        broker="robinhood",
        source=AccountSource.rh_sync,
        balance=30000.00,
    )
    assert a.holdings == []
    assert a.cash == 0


def test_accounts_file_roundtrip():
    payload = {
        "schema_version": 1,
        "last_updated": "2026-04-20T14:00:00-07:00",
        "accounts": [
            {
                "id": "chase",
                "type": "checking",
                "broker": "chase",
                "source": "manual",
                "balance": 12979.47,
                "last_manual_update": "2026-04-20",
            }
        ],
    }
    af = AccountsFile.model_validate(payload)
    assert af.schema_version == 1
    assert len(af.accounts) == 1
    out = af.model_dump(mode="json", exclude_none=True)
    assert out["accounts"][0]["balance"] == 12979.47


def test_accounts_file_rejects_unknown_schema_version():
    with pytest.raises(ValidationError):
        AccountsFile.model_validate({
            "schema_version": 99,
            "last_updated": "2026-04-20T14:00:00-07:00",
            "accounts": [],
        })
