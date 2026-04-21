"""Strategy front-matter schema v1."""
from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrategyState(str, Enum):
    draft = "draft"
    observing = "observing"
    paper = "paper"
    live = "live"
    retired = "retired"


class StrategyMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    name: str
    state: StrategyState
    created_at: date | None = None
    paper_portfolio: str | None = None
    entry_rules: list[str] = []
    exit_rules: list[str] = []
    position_sizing: dict = {}
    advisor_refs: list[str] = []
    history: list[dict] = []
