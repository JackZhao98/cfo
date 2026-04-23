# cfo — Chief Financial Officer

Personal finance CLI for Robinhood users. Part of the 3-layer architecture:

- `rh` (Go) — trades and RH queries
- `cfo` (this) — portfolio management, tradebook, strategies, scheduler, **market DB**
- Skills — Claude's coordination layer

See `../docs/superpowers/specs/2026-04-20-cfo-architecture-design.md` for full design.

## Install

```bash
cd cfo
uv tool install .
```

## Commands

```bash
cfo --help                   # top-level help
cfo sync                     # portfolio + trades + orders + market DB (default)
cfo status                   # unified overview
cfo portfolio show           # accounts table
cfo schedule list            # remote schedule inventory
cfo db status                # market DB row counts + sync watermarks
```

## Market Database

`~/.cfo/data/market.db` is a local SQLite store aggregating all rh-server
schedule run artifacts into structured tables (quotes, indexes, option
chains, news, scans, accounts, activity, dividends, transfers).

Updated automatically by `cfo sync` (or `cfo db sync` to run just the
DB leg). Parser dispatch is based strictly on `meta.command` argv — never
on schedule names, which are user-assigned labels.

Design document: `~/.cfo/data/reports/market-db-plan.md`.

```bash
cfo db sync                  # incremental; uses per-schedule watermarks
cfo db sync --schedule <id>  # target one schedule
cfo db sync --dry-run        # no writes
cfo db status                # audit view
cfo db reset --schedule <id> # force-reprocess a schedule
cfo db vacuum                # compact SQLite
```

Raw SQL queries against `~/.cfo/data/market.db` are encouraged; writing to
the DB manually is not — all inserts should flow through a parser.
