"""Tests for 'cfo price-log' CLI."""
from typer.testing import CliRunner

from cfo.cli import app

runner = CliRunner()


def test_price_log_snap_explicit_symbols(tmp_data_dir, monkeypatch):
    from cfo.core import rh_bridge
    monkeypatch.setattr(
        rh_bridge,
        "quote",
        lambda s: {"symbol": s, "last_price": 100, "updated_at": "2026-04-21T02:10:34Z"},
    )
    r = runner.invoke(app, ["price-log", "snap", "--symbol", "VOO", "--symbol", "QQQM"])
    assert r.exit_code == 0, r.stdout
    assert "2 quote" in r.stdout.lower() or "2 snapped" in r.stdout.lower()


def test_price_log_snap_watchlist_empty(tmp_data_dir, monkeypatch):
    from cfo.core import rh_bridge
    monkeypatch.setattr(
        rh_bridge,
        "quote",
        lambda s: {"symbol": s, "last_price": 100, "updated_at": "2026-04-21T02:10:34Z"},
    )
    r = runner.invoke(app, ["price-log", "snap", "--watchlist"])
    assert r.exit_code == 0
    assert "empty" in r.stdout.lower()


def test_price_log_snap_no_args(tmp_data_dir):
    """No --symbol and no --watchlist → friendly empty message."""
    r = runner.invoke(app, ["price-log", "snap"])
    assert r.exit_code == 0
    assert "empty" in r.stdout.lower()


def test_price_log_show_no_data(tmp_data_dir):
    r = runner.invoke(app, ["price-log", "show", "VOO"])
    assert r.exit_code == 0
    assert "no data" in r.stdout.lower()


def test_price_log_show_with_data(tmp_data_dir, monkeypatch):
    from cfo.core import rh_bridge
    monkeypatch.setattr(
        rh_bridge,
        "quote",
        lambda s: {
            "symbol": s, "last_price": 100.5, "bid": 100.4, "ask": 100.6,
            "high": 101, "low": 99.8, "volume": 12345,
            "updated_at": "2026-04-21T02:10:34Z",
        },
    )
    runner.invoke(app, ["price-log", "snap", "--symbol", "VOO"])
    r = runner.invoke(app, ["price-log", "show", "VOO"])
    assert r.exit_code == 0
    assert "VOO" in r.stdout
    assert "100" in r.stdout
