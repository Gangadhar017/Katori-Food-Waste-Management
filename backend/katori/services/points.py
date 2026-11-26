"""Points for residents who help the kitchen plan: giving notice, rating food, playing while they wait."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..models import PointEvent, User

SKIP_POINTS = 5
SKIPS_REWARDED_PER_DAY = 2  # going home for a week should not top the leaderboard
RATING_POINTS = 2
GAME_MAX_POINTS = 20
GAME_PLAYS_PER_DAY = 3
GAME_SCORE_CAP = {"bin-it": 400, "just-enough": 500}  # scores above this are not humanly reachable


def _touch_streak(user: User, today: date) -> None:
    if user.last_active == today:
        return
    user.streak = user.streak + 1 if user.last_active in (None, today - timedelta(days=1)) else 1
    user.last_active = today


def award(db: Session, user: User, reason: str, ref: str, points: int, today: date) -> int:
    """Credit points once per (reason, ref). Returns the points actually added."""
    exists = db.scalar(
        select(PointEvent.id).where(
            PointEvent.tenant_id == user.tenant_id,
            PointEvent.user_id == user.id,
            PointEvent.reason == reason,
            PointEvent.ref == ref,
        )
    )
    if exists or points <= 0:
        return 0
    db.add(
        PointEvent(
            tenant_id=user.tenant_id, user_id=user.id, reason=reason, ref=ref, points=points, created_at=clock.utcnow()
        )
    )
    user.points += points
    _touch_streak(user, today)
    return points


def revoke(db: Session, user: User, reason: str, ref: str) -> int:
    event = db.scalar(
        select(PointEvent).where(
            PointEvent.tenant_id == user.tenant_id,
            PointEvent.user_id == user.id,
            PointEvent.reason == reason,
            PointEvent.ref == ref,
        )
    )
    if event is None:
        return 0
    user.points = max(user.points - event.points, 0)
    db.delete(event)
    return event.points


def skip_points(db: Session, user: User, day: date, today: date) -> int:
    """Points for one more on-time skip on `day`, respecting the daily cap."""
    rewarded = db.scalar(
        select(func.count())
        .select_from(PointEvent)
        .where(
            PointEvent.tenant_id == user.tenant_id,
            PointEvent.user_id == user.id,
            PointEvent.reason == "skip",
            PointEvent.ref.like(f"{day.isoformat()}:%"),
        )
    )
    return SKIP_POINTS if (rewarded or 0) < SKIPS_REWARDED_PER_DAY else 0


def game_points(game: str, score: int) -> int:
    cap = GAME_SCORE_CAP[game]
    return round(GAME_MAX_POINTS * min(max(score, 0), cap) / cap)


def game_plays_today(db: Session, user: User, game: str, today: date) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(PointEvent)
            .where(
                PointEvent.tenant_id == user.tenant_id,
                PointEvent.user_id == user.id,
                PointEvent.reason == "game",
                PointEvent.ref.like(f"{today.isoformat()}:{game}:%"),
            )
        )
        or 0
    )


def rank_of(db: Session, user: User) -> int:
    ahead = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == user.tenant_id, User.role == "student", User.points > user.points)
    )
    return int(ahead or 0) + 1
