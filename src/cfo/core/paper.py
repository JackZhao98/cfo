"""Paper portfolio management."""
import json
from datetime import date
from pathlib import Path

from cfo.core import strategy as strategy_core
from cfo.schemas.paper import PaperKind, PaperMeta
from cfo.util import atomic, paths


def _paper_dir(kind: PaperKind, pid: str) -> Path:
    base = paths.paper_strategies_dir() if kind == PaperKind.strategy else paths.paper_composite_dir()
    return base / pid


def _find_dir(pid: str) -> Path:
    for kind in (PaperKind.strategy, PaperKind.composite):
        d = _paper_dir(kind, pid)
        if d.exists():
            return d
    raise FileNotFoundError(f"paper portfolio not found: {pid}")


def create(kind: PaperKind, pid: str, capital: float, strategy_ref: str | None = None) -> None:
    d = _paper_dir(kind, pid)
    if d.exists():
        raise FileExistsError(f"paper portfolio already exists: {pid}")
    if kind == PaperKind.strategy:
        if not strategy_ref:
            raise ValueError("strategy_ref is required for strategy paper portfolios")
        strategy_meta = strategy_core.load_meta(strategy_ref)
        if strategy_meta.paper_portfolio and strategy_meta.paper_portfolio != pid:
            raise ValueError(
                f"strategy {strategy_ref} already bound to paper portfolio "
                f"{strategy_meta.paper_portfolio}"
            )
    d.mkdir(parents=True)
    meta = PaperMeta(
        id=pid, kind=kind, strategy_ref=strategy_ref,
        capital_start=capital, capital_current=capital,
        created_at=date.today(), status="active",
    )
    atomic.write_json(d / "meta.json", meta.model_dump(mode="json", exclude_none=True))
    atomic.write_json(d / "portfolio.json", {"schema_version": 1, "holdings": [], "cash": capital})
    (d / "trades.jsonl").touch()
    if kind == PaperKind.strategy:
        strategy_core.set_paper_portfolio(strategy_ref, pid)


def load_meta(pid: str) -> PaperMeta:
    d = _find_dir(pid)
    return PaperMeta.model_validate(json.loads((d / "meta.json").read_text(encoding="utf-8")))


def list_all() -> list[PaperMeta]:
    out: list[PaperMeta] = []
    for base in (paths.paper_strategies_dir(), paths.paper_composite_dir()):
        if not base.exists():
            continue
        for sub in sorted(base.iterdir()):
            meta_file = sub / "meta.json"
            if meta_file.exists():
                out.append(PaperMeta.model_validate(json.loads(meta_file.read_text(encoding="utf-8"))))
    return out


def close(pid: str) -> None:
    d = _find_dir(pid)
    meta = load_meta(pid)
    new_meta = meta.model_copy(update={"status": "closed", "closed_at": date.today()})
    atomic.write_json(d / "meta.json", new_meta.model_dump(mode="json", exclude_none=True))
    if meta.kind == PaperKind.strategy and meta.strategy_ref:
        strategy_meta = strategy_core.load_meta(meta.strategy_ref)
        if strategy_meta.paper_portfolio == pid:
            strategy_core.set_paper_portfolio(meta.strategy_ref, None)
