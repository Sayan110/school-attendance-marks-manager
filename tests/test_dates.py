"""Date helpers used by attendance, analytics and reports."""
from __future__ import annotations

import re
from datetime import date, datetime

from app.utils import dates


def test_iso_and_parse_roundtrip():
    assert dates.iso(date(2026, 10, 5)) == "2026-10-05"
    assert dates.iso(datetime(2026, 10, 5, 14, 30)) == "2026-10-05"
    assert dates.iso("2026-10-05") == "2026-10-05"
    assert dates.iso(None) is None
    assert dates.parse("2026-10-05") == date(2026, 10, 5)
    assert dates.parse("2026-10-05T12:00:00") == date(2026, 10, 5)
    assert dates.parse("") is None
    assert dates.parse(None) is None
    assert dates.parse("not-a-date") is None


def test_display_formats():
    assert dates.display("2026-10-05") == "05-10-2026"
    assert dates.display("bad") == "—"
    assert dates.display(None) == "—"
    assert dates.display_long("2026-10-05") == "05 October 2026"
    assert dates.display_long("bad") == "—"


def test_month_and_week_bounds():
    assert dates.month_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert dates.month_bounds(2028, 2) == (date(2028, 2, 1), date(2028, 2, 29))
    # 2026-10-07 is a Wednesday, so the week starts on Monday 2026-10-05.
    assert dates.week_bounds(date(2026, 10, 7)) == (date(2026, 10, 5), date(2026, 10, 11))
    assert dates.week_bounds(date(2026, 10, 5))[0] == date(2026, 10, 5)


def test_month_labels_and_lengths():
    assert dates.month_name(10) == "October"
    assert dates.month_label(2026, 10) == "October 2026"
    assert dates.days_in_month(2026, 2) == 28
    assert dates.days_in_month(2028, 2) == 29


def test_daterange_inclusive_and_reversible():
    days = dates.daterange(date(2026, 10, 1), date(2026, 10, 5))
    assert len(days) == 5
    assert days[0] == date(2026, 10, 1) and days[-1] == date(2026, 10, 5)
    reversed_days = dates.daterange(date(2026, 10, 5), date(2026, 10, 1))
    assert reversed_days == days
    assert dates.daterange(date(2026, 10, 1), date(2026, 10, 1)) == [date(2026, 10, 1)]


def test_months_between_spans_years():
    months = dates.months_between(date(2026, 11, 1), date(2027, 2, 28))
    assert months == [(2026, 11), (2026, 12), (2027, 1), (2027, 2)]
    assert dates.months_between(date(2027, 2, 1), date(2026, 11, 1)) == months
    assert dates.months_between(date(2026, 10, 1), date(2026, 10, 31)) == [(2026, 10)]


def test_current_session_name_format():
    name = dates.current_session_name()
    assert re.fullmatch(r"\d{4}-\d{4}", name)
    start = int(name[:4])
    assert int(name[-4:]) == start + 1
