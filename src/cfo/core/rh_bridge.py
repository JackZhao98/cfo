"""Bridge to rh CLI via subprocess."""
import json
import subprocess


def snapshot() -> dict:
    """Run `rh account snapshot --format json` and parse output."""
    result = subprocess.run(
        ["rh", "account", "snapshot", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rh failed: {result.stderr.strip() or 'unknown error'}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh output not JSON: {e}")


def quote(symbol: str) -> dict:
    """Run `rh quote SYMBOL --format json` and parse output."""
    result = subprocess.run(
        ["rh", "quote", symbol, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh quote {symbol} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh quote {symbol} output not JSON: {e}")


def quotes(symbols: list[str]) -> dict:
    """Run batched `rh quote ... --format json` and parse output.

    Returns either the batched shape ``{"count": N, "quotes": [...]}`` or a
    single-quote flat dict, depending on what the CLI emits for the given
    symbol count. The caller should handle both.
    """
    if not symbols:
        return {"count": 0, "quotes": []}
    result = subprocess.run(
        ["rh", "quote", *symbols, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh quote {' '.join(symbols)} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh quote batch output not JSON: {e}")


def index_list() -> list[str]:
    """Return symbols registered in `rh index --list`."""
    result = subprocess.run(
        ["rh", "index", "--list", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rh index --list failed: {result.stderr.strip() or 'unknown'}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh index --list not JSON: {e}")
    return [row["symbol"] for row in data.get("indexes", [])]


def index_values(symbols: list[str]) -> list[dict]:
    """Run `rh index SYM1 SYM2 ... --format json` and return merged rows."""
    if not symbols:
        return []
    result = subprocess.run(
        ["rh", "index", *symbols, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh index {' '.join(symbols)} failed: {result.stderr.strip() or 'unknown'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh index output not JSON: {e}")


def order(order_id: str) -> dict:
    """Run `rh order ORDER_ID --format json` and parse output."""
    result = subprocess.run(
        ["rh", "order", order_id, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh order {order_id} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh order {order_id} output not JSON: {e}")


def activity(limit: int = 50) -> dict:
    """Run `rh activity --limit N --format json` and parse output."""
    result = subprocess.run(
        ["rh", "activity", "--limit", str(limit), "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh activity --limit {limit} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh activity output not JSON: {e}")


def bars(symbol: str, from_date: str, to_date: str, interval: str = "day") -> dict:
    """Run `rh bars SYMBOL --from D --to D --interval X --format json`."""
    result = subprocess.run(
        ["rh", "bars", symbol, "--from", from_date, "--to", to_date, "--interval", interval, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh bars {symbol} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh bars {symbol} output not JSON: {e}")


def symbol_news(symbol: str) -> dict:
    """Run `rh symbol news SYMBOL --format json` and parse output."""
    result = subprocess.run(
        ["rh", "symbol", "news", symbol, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh symbol news {symbol} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh symbol news {symbol} output not JSON: {e}")


def symbol_earnings(symbol: str) -> dict:
    """Run `rh symbol earnings SYMBOL --format json` and parse output."""
    result = subprocess.run(
        ["rh", "symbol", "earnings", symbol, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh symbol earnings {symbol} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh symbol earnings {symbol} output not JSON: {e}")


def option_expirations(symbol: str) -> dict:
    """Run `rh option expirations SYMBOL --format json` and parse output."""
    result = subprocess.run(
        ["rh", "option", "expirations", symbol, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh option expirations {symbol} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh option expirations {symbol} output not JSON: {e}")


def option_chain(symbol: str, exp: str, option_type: str = "put") -> dict:
    """Run `rh option chain SYMBOL --exp D --type T --format json`."""
    result = subprocess.run(
        ["rh", "option", "chain", symbol, "--exp", exp, "--type", option_type, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"rh option chain {symbol} {exp} failed: {result.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"rh option chain {symbol} {exp} output not JSON: {e}")
