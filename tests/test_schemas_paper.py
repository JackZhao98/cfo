from datetime import date

import pytest
from pydantic import ValidationError

from cfo.schemas.paper import PaperMeta, PaperKind


def test_paper_strategy_meta():
    m = PaperMeta(
        id="wheel-sofi-2k", kind=PaperKind.strategy,
        strategy_ref="wheel-sofi", capital_start=2000.0,
        capital_current=2000.0, created_at=date.today(), status="active",
    )
    assert m.schema_version == 1


def test_paper_composite_no_strategy_ref():
    m = PaperMeta(
        id="jack-sim-55k", kind=PaperKind.composite,
        capital_start=55000, capital_current=55000,
        created_at=date.today(), status="active",
    )
    assert m.strategy_ref is None
