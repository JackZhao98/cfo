"""SQLite connection helper + schema migration for the market DB."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from cfo.market_db import schema
from cfo.util import paths


class MarketDBError(RuntimeError):
    """Raised for market DB operational errors."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path() -> Path:
    return paths.market_db()


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(read_only: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a connection; DB file and schema auto-created on first use."""
    p = db_path()
    _ensure_parent(p)
    if read_only and not p.exists():
        raise MarketDBError(f"market DB does not exist yet: {p}")
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        if not read_only:
            _apply_migrations(conn)
        yield conn
        if not read_only:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> Path:
    """Idempotent: create DB file + apply all pending migrations."""
    with connect() as _:
        pass
    return db_path()


def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute(schema.SCHEMA_VERSION_DDL)
    cur = conn.execute("SELECT MAX(version) FROM schema_version")
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _apply_migrations(conn: sqlite3.Connection) -> None:
    current = _current_version(conn)
    for version, description, statements in schema.MIGRATIONS:
        if version <= current:
            continue
        for ddl in statements:
            # DDL blocks may contain multiple statements separated by ``;``.
            conn.executescript(ddl)
        conn.execute(
            "INSERT INTO schema_version(version, applied_at, description) VALUES (?, ?, ?)",
            (version, _utc_now(), description),
        )
