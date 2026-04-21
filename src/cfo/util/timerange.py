"""ISO week / month date math helpers."""
from calendar import monthrange
from datetime import date, datetime, timedelta


def iso_week_bounds(d: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of ISO week containing d."""
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def iso_week_id(d: date) -> str:
    """Return 'YYYY-WNN' for the ISO week of d."""
    y, w, _ = d.isocalendar()
    return f"{y:04d}-W{w:02d}"


def month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    _, last_day = monthrange(d.year, d.month)
    last = d.replace(day=last_day)
    return first, last


def month_id(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def last_week_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    this_mon, _ = iso_week_bounds(today)
    last_mon = this_mon - timedelta(days=7)
    last_sun = this_mon - timedelta(days=1)
    return last_mon, last_sun


def last_month_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    first_of_this = today.replace(day=1)
    last_of_prev = first_of_this - timedelta(days=1)
    return month_bounds(last_of_prev)


def datetime_in_range(dt: datetime, start: date, end: date) -> bool:
    """Inclusive on both ends (compares local date part).

    Timezone-aware datetimes are converted to the local timezone before the
    date extraction so comparisons against `date.today()`-derived bounds
    behave consistently.
    """
    if isinstance(dt, datetime):
        d = dt.astimezone().date() if dt.tzinfo is not None else dt.date()
    else:
        d = dt
    return start <= d <= end
