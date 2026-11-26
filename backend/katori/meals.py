"""The four sittings of a hostel mess day and the clock rules around them."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

from . import clock

MEALS: tuple[str, ...] = ("breakfast", "lunch", "snacks", "dinner")
MEAL_INDEX = {meal: index for index, meal in enumerate(MEALS)}

WINDOWS: dict[str, tuple[time, time]] = {
    "breakfast": (time(7, 30), time(9, 30)),
    "lunch": (time(12, 30), time(14, 30)),
    "snacks": (time(17, 0), time(18, 0)),
    "dinner": (time(19, 30), time(21, 30)),
}

# A skip only saves food if the kitchen hears about it before it starts cooking.
CUTOFF_HOURS = 3


def window_utc(day: date, meal: str, tz: str) -> tuple[datetime, datetime]:
    start, end = WINDOWS[meal]
    return clock.to_utc(datetime.combine(day, start), tz), clock.to_utc(datetime.combine(day, end), tz)


def cutoff_utc(day: date, meal: str, tz: str) -> datetime:
    return window_utc(day, meal, tz)[0] - timedelta(hours=CUTOFF_HOURS)


def iter_slots(first: date, last: date) -> Iterator[tuple[date, str]]:
    day = first
    while day <= last:
        for meal in MEALS:
            yield day, meal
        day += timedelta(days=1)


def current_or_next(now_utc: datetime, tz: str) -> tuple[date, str, str]:
    """The sitting that is open now, or the next one to open.

    Returns (day, meal, phase) where phase is "open" or "upcoming".
    """
    today = clock.to_local(now_utc, tz).date()
    for day, meal in iter_slots(today, today + timedelta(days=1)):
        start, end = window_utc(day, meal, tz)
        if now_utc < start:
            return day, meal, "upcoming"
        if now_utc < end:
            return day, meal, "open"
    raise RuntimeError("no sitting found in the next two days")  # pragma: no cover


def last_finished(now_utc: datetime, tz: str) -> tuple[date, str]:
    today = clock.to_local(now_utc, tz).date()
    latest: tuple[date, str] | None = None
    for day, meal in iter_slots(today - timedelta(days=1), today):
        if window_utc(day, meal, tz)[1] <= now_utc:
            latest = (day, meal)
    assert latest is not None
    return latest
