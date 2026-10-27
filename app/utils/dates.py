"""Date helpers used across services, UI and reports."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta


def today() -> date:
    return date.today()


def iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def parse(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def display(value: str | date | None) -> str:
    parsed = parse(value)
    return parsed.strftime("%d-%m-%Y") if parsed else "—"


def display_long(value: str | date | None) -> str:
    parsed = parse(value)
    return parsed.strftime("%d %B %Y") if parsed else "—"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def week_bounds(anchor: date) -> tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def month_name(month: int) -> str:
    return calendar.month_name[month]


def month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def daterange(start: date, end: date) -> list[date]:
    if end < start:
        start, end = end, start
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    if end < start:
        start, end = end, start
    result: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        result.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return result


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def current_session_name() -> str:
    now = date.today()
    start_year = now.year if now.month >= 4 else now.year - 1
    return f"{start_year}-{start_year + 1}"
