"""One place that answers "what time is it", so tests and the simulator can pin it.

Timestamps are stored as naive UTC. Calendar days are the kitchen's local days.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

_frozen: datetime | None = None


def utcnow() -> datetime:
    if _frozen is not None:
        return _frozen
    return datetime.now(UTC).replace(tzinfo=None)


def freeze(moment: datetime | None) -> None:
    """Pin the clock to a naive UTC moment; pass None to release it."""
    global _frozen
    _frozen = moment


def to_local(moment_utc: datetime, tz: str) -> datetime:
    return moment_utc.replace(tzinfo=UTC).astimezone(ZoneInfo(tz)).replace(tzinfo=None)


def to_utc(moment_local: datetime, tz: str) -> datetime:
    return moment_local.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC).replace(tzinfo=None)


def local_today(tz: str) -> date:
    return to_local(utcnow(), tz).date()


def iso_utc(moment: datetime | None) -> str | None:
    """Serialise a stored naive-UTC timestamp so browsers parse it as UTC."""
    return None if moment is None else moment.isoformat(timespec="seconds") + "Z"
