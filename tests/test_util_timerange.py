from datetime import date, datetime, timezone

from cfo.util import timerange as tr


def test_iso_week_bounds():
    # 2026-04-20 is a Monday (ISO week 17 of 2026)
    start, end = tr.iso_week_bounds(date(2026, 4, 20))
    assert start == date(2026, 4, 20)  # Monday
    assert end == date(2026, 4, 26)    # Sunday


def test_iso_week_midweek():
    # Wednesday 2026-04-22
    start, end = tr.iso_week_bounds(date(2026, 4, 22))
    assert start == date(2026, 4, 20)
    assert end == date(2026, 4, 26)


def test_iso_week_id():
    assert tr.iso_week_id(date(2026, 4, 22)) == "2026-W17"


def test_month_bounds():
    start, end = tr.month_bounds(date(2026, 4, 15))
    assert start == date(2026, 4, 1)
    assert end == date(2026, 4, 30)


def test_month_bounds_december():
    start, end = tr.month_bounds(date(2026, 12, 15))
    assert start == date(2026, 12, 1)
    assert end == date(2026, 12, 31)


def test_month_id():
    assert tr.month_id(date(2026, 4, 20)) == "2026-04"


def test_last_week_bounds():
    # Given today 2026-04-22 (Wednesday W17), last week = W16 = Apr 13-19
    start, end = tr.last_week_bounds(today=date(2026, 4, 22))
    assert start == date(2026, 4, 13)
    assert end == date(2026, 4, 19)


def test_last_month_bounds():
    # Given today 2026-04-15, last month = March 2026
    start, end = tr.last_month_bounds(today=date(2026, 4, 15))
    assert start == date(2026, 3, 1)
    assert end == date(2026, 3, 31)


def test_last_month_january():
    # Jan → previous = Dec of prior year
    start, end = tr.last_month_bounds(today=date(2026, 1, 15))
    assert start == date(2025, 12, 1)
    assert end == date(2025, 12, 31)


def test_datetime_in_range():
    start = date(2026, 4, 13)
    end = date(2026, 4, 19)
    in_range = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    out_of_range = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    assert tr.datetime_in_range(in_range, start, end) is True
    assert tr.datetime_in_range(out_of_range, start, end) is False
