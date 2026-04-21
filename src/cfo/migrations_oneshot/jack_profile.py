"""Copy legacy jack-profile.md → data/portfolio/profile.md with a migration banner."""
from datetime import date
from pathlib import Path


BANNER = "> _Migrated from skills/investing/jack-profile.md on {today}_\n\n"


def copy(src: Path, dst: Path) -> None:
    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    original = src.read_text(encoding="utf-8")
    dst.write_text(
        BANNER.format(today=date.today().isoformat()) + original,
        encoding="utf-8",
    )
