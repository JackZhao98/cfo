"""Parser dispatch — ROUTES BY COMMAND ARGV ONLY.

**Discipline**: schedule names are user-assigned labels that may be
arbitrary (``my-test-1``, ``whatever``). The ONLY authoritative routing
signal is ``meta.command`` — the actual argv that the rh binary ran.

Longest-prefix match wins. Subcommand tokens are considered (``--flag``
options are stripped before matching).
"""
from __future__ import annotations

from typing import Sequence


# (command_prefix_tuple) -> parser_name
PARSER_REGISTRY: dict[tuple[str, ...], str] = {
    ("rh", "quote"): "parse_quote",
    ("rh", "index"): "parse_index",
    ("rh", "option", "chain"): "parse_option_chain",
    ("rh", "option", "positions"): "parse_option_positions",
    ("rh", "option", "expirations"): "parse_option_expirations",
    ("rh", "option", "history"): "parse_option_history",
    ("rh", "symbol", "news"): "parse_news",
    ("rh", "symbol", "earnings"): "parse_earnings",
    ("rh", "symbol", "ratings"): "parse_ratings",
    ("rh", "symbol", "similar"): "parse_similar",
    ("rh", "symbol", "tags"): "parse_tags",
    ("rh", "symbol", "splits"): "parse_splits",
    ("rh", "symbol", "search"): "parse_symbol_search",
    ("rh", "scan"): "parse_scan",
    ("rh", "movers"): "parse_sp500_movers",
    ("rh", "account", "list"): "parse_account_list",
    ("rh", "account", "show"): "parse_account_show",
    ("rh", "account", "snapshot"): "parse_account_snapshot",
    ("rh", "activity"): "parse_activity",
    ("rh", "dividends"): "parse_dividends",
    ("rh", "transfers"): "parse_transfers",
    ("rh", "market"): "parse_market_status",
    ("rh", "margin"): "parse_margin",
    ("rh", "pdt"): "parse_pdt",
    ("rh", "gold"): "parse_gold",
    ("rh", "bars"): "parse_bars",
    ("rh", "crypto", "quote"): "parse_crypto_quote",
    ("rh", "crypto", "holdings"): "parse_crypto_holdings",
    ("rh", "watchlist", "list"): "parse_watchlist_list",
    ("rh", "watchlist", "show"): "parse_watchlist_show",
    ("rh", "notifications"): "parse_notifications",
    ("rh", "documents"): "parse_documents",
    ("rh", "order"): "parse_order_detail",
}


def _strip_options(command: Sequence[str]) -> list[str]:
    """Drop ``--flag value`` style options, keep positional subcommand tokens.

    We keep positional args because some registry entries might want to
    look at them (e.g. future: differentiate by symbol). For now only the
    leading subcommand path matters.
    """
    out: list[str] = []
    skip_next = False
    for token in command:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("--"):
            # Be conservative: assume the next token is its value unless
            # the flag itself contains ``=`` (``--foo=bar``).
            if "=" not in token:
                skip_next = True
            continue
        if token.startswith("-") and len(token) > 1 and not token[1].isdigit():
            if "=" not in token:
                skip_next = True
            continue
        out.append(token)
    return out


def dispatch_parser(command: Sequence[str]) -> str | None:
    """Return the registered parser name, or ``None`` if unknown.

    Matches the longest registered prefix of the stripped command path.
    """
    if not command:
        return None
    path = _strip_options(command)
    if not path:
        return None
    # Longest-match wins; try deeper prefixes first.
    max_depth = max((len(k) for k in PARSER_REGISTRY), default=0)
    for depth in range(min(max_depth, len(path)), 0, -1):
        key = tuple(path[:depth])
        if key in PARSER_REGISTRY:
            return PARSER_REGISTRY[key]
    return None
