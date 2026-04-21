"""Paper portfolio meta schema."""
from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, NonNegativeFloat


class PaperKind(str, Enum):
    strategy = "strategy"
    composite = "composite"


class PaperMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    id: str
    kind: PaperKind
    strategy_ref: str | None = None
    capital_start: NonNegativeFloat
    capital_current: NonNegativeFloat
    created_at: date
    status: Literal["active", "closed"] = "active"
    closed_at: date | None = None
