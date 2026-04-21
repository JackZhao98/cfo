"""Strategy lifecycle: new / list / transition."""
from datetime import date
from pathlib import Path

from cfo.schemas.strategy import StrategyMeta, StrategyState
from cfo.util import paths, yaml_io


ALLOWED_TRANSITIONS: dict[StrategyState, set[StrategyState]] = {
    StrategyState.draft: {StrategyState.observing, StrategyState.retired},
    StrategyState.observing: {StrategyState.paper, StrategyState.retired},
    StrategyState.paper: {StrategyState.live, StrategyState.retired},
    StrategyState.live: {StrategyState.retired},
    StrategyState.retired: set(),
}


_TEMPLATES: dict[str, dict] = {
    "wheel": {
        "entry_rules": ["IV rank > 40", "30-45 DTE", "Delta 0.15-0.25"],
        "exit_rules": ["50% profit → close", "21 DTE → roll or close", "Assignment OK (wheel)"],
        "position_sizing": {"max_contracts_per_symbol": 2, "max_notional_pct": 20},
    },
    "dca": {
        "entry_rules": ["Fixed monthly amount", "No market timing"],
        "exit_rules": ["Hold indefinitely"],
        "position_sizing": {"monthly_usd": 1000},
    },
    "blank": {"entry_rules": [], "exit_rules": [], "position_sizing": {}},
}


def _yaml_path(name: str) -> Path:
    return paths.strategies_dir() / f"{name}.yaml"


def _md_path(name: str) -> Path:
    return paths.strategies_dir() / f"{name}.md"


def new_strategy(name: str, template: str = "blank") -> None:
    if _yaml_path(name).exists():
        raise FileExistsError(f"strategy already exists: {name}")
    today = date.today()
    tpl = _TEMPLATES.get(template, _TEMPLATES["blank"])
    meta = StrategyMeta(
        name=name,
        state=StrategyState.draft,
        created_at=today,
        entry_rules=list(tpl["entry_rules"]),
        exit_rules=list(tpl["exit_rules"]),
        position_sizing=dict(tpl["position_sizing"]),
        history=[{"date": today.isoformat(), "event": "created"}],
    )
    _save_meta(meta)
    _md_path(name).write_text(
        f"# {name}\n\n*Created {today.isoformat()} from template `{template}`.*\n\n"
        f"State: `{meta.state.value}`\n\n## Notes\n\n(add your notes here)\n",
        encoding="utf-8",
    )


def _save_meta(meta: StrategyMeta) -> None:
    yaml_io.dump_yaml(
        _yaml_path(meta.name),
        meta.model_dump(mode="json", exclude_none=False),
    )


def load_meta(name: str) -> StrategyMeta:
    p = _yaml_path(name)
    if not p.exists():
        raise FileNotFoundError(f"strategy not found: {name}")
    return StrategyMeta.model_validate(yaml_io.load_yaml(p))


def list_strategies() -> list[StrategyMeta]:
    d = paths.strategies_dir()
    if not d.exists():
        return []
    metas: list[StrategyMeta] = []
    for yml in sorted(d.glob("*.yaml")):
        metas.append(StrategyMeta.model_validate(yaml_io.load_yaml(yml)))
    return metas


def transition(name: str, to: StrategyState) -> None:
    meta = load_meta(name)
    if to not in ALLOWED_TRANSITIONS[meta.state]:
        raise ValueError(
            f"illegal transition {meta.state.value} → {to.value} "
            f"(allowed: {sorted(s.value for s in ALLOWED_TRANSITIONS[meta.state])})"
        )
    new_history = meta.history + [
        {"date": date.today().isoformat(), "event": f"state: {meta.state.value} → {to.value}"}
    ]
    new_meta = meta.model_copy(update={"state": to, "history": new_history})
    _save_meta(new_meta)
