"""YAML safe load/dump."""
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump_yaml(path: Path, data: Any) -> None:
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    # atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
