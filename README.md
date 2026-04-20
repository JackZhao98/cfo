# cfo — Chief Financial Officer

Personal finance CLI for Robinhood users. Part of the 3-layer architecture:

- `rh` (Go) — trades and RH queries
- `cfo` (this) — portfolio management, tradebook, strategies, scheduler
- Skills — Claude's coordination layer

See `../docs/superpowers/specs/2026-04-20-cfo-architecture-design.md` for full design.

## Install

```bash
cd cfo
uv tool install .
```

## Commands

```bash
cfo --help
cfo portfolio show
```
