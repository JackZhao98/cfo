"""profile.md — user descriptive profile (MD, AI-writable)."""
from cfo.util import paths


def load() -> str | None:
    p = paths.profile_md()
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def save(content: str) -> None:
    p = paths.profile_md()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
