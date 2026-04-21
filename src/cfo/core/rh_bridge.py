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
