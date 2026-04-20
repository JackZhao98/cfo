"""Portfolio schema v1."""
from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat


class AccountType(str, Enum):
    taxable = "taxable"
    roth_ira = "roth_ira"
    traditional_ira = "traditional_ira"
    checking = "checking"
    savings = "savings"
    hysa = "hysa"
    other = "other"


class AccountSource(str, Enum):
    rh_sync = "rh_sync"
    manual = "manual"


class Holding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str
    qty: NonNegativeFloat
    cost_basis: NonNegativeFloat = 0


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: AccountType
    broker: str
    source: AccountSource
    balance: NonNegativeFloat
    cash: NonNegativeFloat = 0
    holdings: list[Holding] = Field(default_factory=list)
    last_manual_update: date | None = None


class AccountsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    last_updated: datetime
    accounts: list[Account]
