"""Portfolio accounts load/save/update.

Never mutates in place — always returns a new AccountsFile and overwrites.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

from cfo.schemas.portfolio import Account, AccountsFile
from cfo.util import atomic, paths


def _empty() -> AccountsFile:
    return AccountsFile(
        schema_version=1,
        last_updated=datetime.now(timezone.utc),
        accounts=[],
    )


def load() -> AccountsFile:
    p = paths.accounts_json()
    if not p.exists():
        return _empty()
    raw = json.loads(p.read_text(encoding="utf-8"))
    return AccountsFile.model_validate(raw)


def save(af: AccountsFile) -> None:
    af_fresh = af.model_copy(update={"last_updated": datetime.now(timezone.utc)})
    atomic.write_json(paths.accounts_json(), af_fresh.model_dump(mode="json", exclude_none=True))


def update_balance(account_id: str, balance: float, manual_date: Optional[date] = None) -> None:
    af = load()
    found = False
    new_accounts = []
    for a in af.accounts:
        if a.id == account_id:
            new_accounts.append(a.model_copy(update={
                "balance": balance,
                "last_manual_update": manual_date or date.today(),
            }))
            found = True
        else:
            new_accounts.append(a)
    if not found:
        raise KeyError(f"account not found: {account_id}")
    save(af.model_copy(update={"accounts": new_accounts}))


def add_account(account: Account) -> None:
    af = load()
    if any(a.id == account.id for a in af.accounts):
        raise ValueError(f"account id already exists: {account.id}")
    save(af.model_copy(update={"accounts": af.accounts + [account]}))
