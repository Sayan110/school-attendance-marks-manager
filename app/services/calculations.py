"""Pure calculation helpers (no database / UI dependencies)."""
from __future__ import annotations

import statistics
from typing import Any, Iterable, Mapping, Sequence


def attendance_percentage(
    present: int,
    absent: int,
    leave: int = 0,
    exclude_leave: bool = True,
) -> float | None:
    """Present sessions / counted sessions * 100.

    Unmarked sessions are never part of the inputs, so they cannot count as
    absences. When ``exclude_leave`` is True, Leave sessions are removed from
    the denominator.
    """
    present = max(0, int(present or 0))
    absent = max(0, int(absent or 0))
    leave = max(0, int(leave or 0))
    counted = present + absent + (0 if exclude_leave else leave)
    if counted <= 0:
        return None
    return round(present / counted * 100, 2)


def effective_pass_marks(
    max_marks: float | None,
    pass_marks: float | None = None,
    pass_percent: float | None = None,
) -> float | None:
    if pass_marks is not None:
        return float(pass_marks)
    if pass_percent is not None:
        return round(float(max_marks or 0) * float(pass_percent) / 100.0, 2)
    return None


def is_pass(
    total: float | None,
    max_marks: float | None,
    pass_marks: float | None = None,
    pass_percent: float | None = None,
) -> bool | None:
    """None when the mark is missing / absent / exempted."""
    if total is None:
        return None
    threshold = effective_pass_marks(max_marks, pass_marks, pass_percent)
    if threshold is None:
        return None
    return float(total) >= threshold


def percentage(total: float | None, max_marks: float | None) -> float | None:
    if total is None or not max_marks:
        return None
    return round(float(total) / float(max_marks) * 100, 2)


def competition_ranks(values: Mapping[Any, float | None], descending: bool = True) -> dict[Any, int]:
    """Standard competition ranking: ties share a rank, the next rank skips.

    Example (descending): 90 -> 1, 80 -> 2, 80 -> 2, 70 -> 4.
    Missing values receive no rank (they are omitted from the result).
    """
    present = [(key, float(value)) for key, value in values.items() if value is not None]
    if not present:
        return {}
    present.sort(key=lambda item: item[1], reverse=descending)
    ranks: dict[Any, int] = {}
    previous_value: float | None = None
    previous_rank = 0
    for index, (key, value) in enumerate(present, start=1):
        if previous_value is not None and abs(value - previous_value) < 1e-9:
            ranks[key] = previous_rank
        else:
            ranks[key] = index
            previous_rank = index
            previous_value = value
    return ranks


def summarize(values: Iterable[float | None]) -> dict[str, float | int | None]:
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return {
            "count": 0,
            "highest": None,
            "lowest": None,
            "average": None,
            "median": None,
            "total": 0.0,
        }
    return {
        "count": len(cleaned),
        "highest": round(max(cleaned), 2),
        "lowest": round(min(cleaned), 2),
        "average": round(sum(cleaned) / len(cleaned), 2),
        "median": round(statistics.median(cleaned), 2),
        "total": round(sum(cleaned), 2),
    }


def grade_for(percent: float | None, rules: Sequence[Mapping[str, Any]]) -> str:
    if percent is None:
        return "—"
    for rule in rules:
        low = float(rule["min_percent"])
        high = float(rule["max_percent"])
        if low <= percent <= high + 1e-9:
            return str(rule["grade"])
    return "—"


def rate(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return round(part / whole * 100, 2)


def percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 2)


def support_flag(
    average_percent: float | None,
    attendance: float | None,
    performance_threshold: float,
    attendance_threshold: float,
) -> bool:
    """True when either marks or attendance is below the configured thresholds."""
    if average_percent is not None and average_percent < performance_threshold:
        return True
    if attendance is not None and attendance < attendance_threshold:
        return True
    return False
