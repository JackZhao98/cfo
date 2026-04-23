"""Market database — local SQLite that aggregates rh-server run artifacts.

Architecture:
  rh-server (SSOT)  →  sync layer  →  SQLite (query layer)

Purpose:
  Server stores raw JSON per run; this DB restructures them into typed
  tables for backtesting, time-series queries, and reports.

Routing discipline:
  Parser dispatch is based ONLY on ``meta.command`` (the authoritative
  argv that was executed). Schedule names are user-assigned labels and
  MUST NOT drive logic. See dispatch.py.
"""
from cfo.market_db.connection import connect, init_db, MarketDBError
from cfo.market_db.dispatch import dispatch_parser, PARSER_REGISTRY
from cfo.market_db.sync import sync_market_data, SyncResult

__all__ = [
    "connect",
    "init_db",
    "MarketDBError",
    "dispatch_parser",
    "PARSER_REGISTRY",
    "sync_market_data",
    "SyncResult",
]
