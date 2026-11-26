"""What a resident does: read the food chart, give notice, rate, queue, play, climb the board."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..db import get_db
from ..meals import MEAL_INDEX, MEALS, cutoff_utc, window_utc
from ..models import CalendarDay, Dish, DishService, GameScore, MealService, MenuEntry, PointEvent, Rating, Rsvp, Tenant, User
from ..security import require_role
from ..services import points
from ..sim.engine import count_skips
from .deps import check_meal, dish_out, kitchen_of, sitting_state

router = APIRouter(prefix="/api", tags=["resident"])
resident = require_role("student")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_AWAY_DAYS = 21


class RsvpBody(BaseModel):
    status: str = Field(pattern="^(eat|skip)$")


class AwayBody(BaseModel):
    start: date
    end: date


class RatingItem(BaseModel):
    dish_id: int
    stars: int = Field(ge=1, le=5)
    portion: str = Field(default="right", pattern="^(less|right|more)$")


class RatingsBody(BaseModel):
    ratings: list[RatingItem] = Field(min_length=1, max_length=12)


class ScoreBody(BaseModel):
    game: str = Field(pattern="^(bin-it|just-enough)$")
    score: int = Field(ge=0, le=100000)


def _days(db: Session, tenant: Tenant, user: User, first: date, count: int) -> list[dict]:
    last = first + timedelta(days=count - 1)
    now = clock.utcnow()
    services = {
        (s.day, s.meal): s
        for s in db.scalars(
            select(MealService).where(MealService.tenant_id == tenant.id, MealService.day.between(first, last))
        )
    }
    menus: dict[tuple, list[Dish]] = {}
    for entry, dish in db.execute(
        select(MenuEntry, Dish)
        .join(Dish, Dish.id == MenuEntry.dish_id)
        .where(MenuEntry.tenant_id == tenant.id, MenuEntry.day.between(first, last))
        .order_by(MenuEntry.position)
    ):
        menus.setdefault((entry.day, entry.meal), []).append(dish)
    notices = {
        (r.day, r.meal): r.status
        for r in db.scalars(select(Rsvp).where(Rsvp.user_id == user.id, Rsvp.day.between(first, last)))
    }
    rated = {
        (day, meal)
        for day, meal in db.execute(
            select(Rating.day, Rating.meal).where(Rating.user_id == user.id, Rating.day.between(first, last)).distinct()
        )
    }
    marked = {
        c.day: c for c in db.scalars(select(CalendarDay).where(CalendarDay.tenant_id == tenant.id, CalendarDay.day.between(first, last)))
    }
    days = []
    for offset in range(count):
        day = first + timedelta(days=offset)
        meals = []
        for meal in MEALS:
            service = services.get((day, meal))
            if service is None:
                continue
            start, end = window_utc(day, meal, tenant.timezone)
            state = sitting_state(now, day, meal, tenant.timezone)
            meals.append(
                {
                    "day": day.isoformat(),
                    "meal": meal,
                    "starts_at": clock.iso_utc(start),
                    "ends_at": clock.iso_utc(end),
                    "cutoff_at": clock.iso_utc(cutoff_utc(day, meal, tenant.timezone)),
                    "state": state,
                    "rsvp": notices.get((day, meal), "eat"),
                    "dishes": [dish_out(d) for d in menus.get((day, meal), [])],
                    "expected": round(service.forecast_p50) if service.forecast_p50 is not None else None,
                    "notices": service.skips,
                    "rated": (day, meal) in rated,
                    "can_rate": state in {"serving", "done"} and notices.get((day, meal), "eat") == "eat",
                }
            )
        note = marked.get(day)
        days.append(
            {
                "day": day.isoformat(),
                "weekday": WEEKDAYS[day.weekday()],
                "calendar": {"kind": note.kind, "label": note.label} if note else None,
                "meals": meals,
            }
        )
    return days


@router.get("/meals")
def meals(
    days: int = Query(7, ge=1, le=8),
    back: int = Query(0, ge=0, le=1),
    user: User = Depends(resident),
    tenant: Tenant = Depends(kitchen_of),
    db: Session = Depends(get_db),
) -> dict:
    today = clock.local_today(tenant.timezone)
    return {
        "today": today.isoformat(),
        "now": clock.iso_utc(clock.utcnow()),
        "points": user.points,
        "streak": user.streak,
        "days": _days(db, tenant, user, today - timedelta(days=back), days + back),
    }


def _set_notice(db: Session, tenant: Tenant, user: User, day: date, meal: str, status: str, today: date) -> int:
    """Record eat/skip for one sitting. Returns points gained (negative if a skip was withdrawn)."""
    row = db.scalar(select(Rsvp).where(Rsvp.tenant_id == tenant.id, Rsvp.user_id == user.id, Rsvp.day == day, Rsvp.meal == meal))
    if row is None:
        row = Rsvp(tenant_id=tenant.id, user_id=user.id, day=day, meal=meal, status=status, updated_at=clock.utcnow())
        db.add(row)
    elif row.status == status:
        return 0
    else:
        row.status, row.updated_at = status, clock.utcnow()
    db.flush()
    service = db.scalar(select(MealService).where(MealService.tenant_id == tenant.id, MealService.day == day, MealService.meal == meal))
    if service is not None:
        service.skips = count_skips(db, tenant.id, day, meal)
    ref = f"{day.isoformat()}:{meal}"
    if status == "skip":
        return points.award(db, user, "skip", ref, points.skip_points(db, user, day, today), today)
    return -points.revoke(db, user, "skip", ref)


@router.put("/meals/{day}/{meal}/rsvp")
def set_rsvp(
    day: date,
    meal: str,
    body: RsvpBody,
    user: User = Depends(resident),
    tenant: Tenant = Depends(kitchen_of),
    db: Session = Depends(get_db),
) -> dict:
    check_meal(meal)
    today = clock.local_today(tenant.timezone)
    if not db.scalar(select(MealService.id).where(MealService.tenant_id == tenant.id, MealService.day == day, MealService.meal == meal)):
        raise HTTPException(404, "That meal is not on the chart yet")
    if clock.utcnow() >= cutoff_utc(day, meal, tenant.timezone):
        raise HTTPException(409, "The kitchen has already started cooking for this meal")
    gained = _set_notice(db, tenant, user, day, meal, body.status, today)
    db.commit()
    return {"meal": _days(db, tenant, user, day, 1)[0]["meals"][MEAL_INDEX[meal]], "points": user.points, "gained": gained, "streak": user.streak}


@router.post("/meals/away")
def mark_away(
    body: AwayBody, user: User = Depends(resident), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)
) -> dict:
    """Going home: skip every sitting between two dates in one go."""
    today = clock.local_today(tenant.timezone)
    if body.end < body.start or body.start < today:
        raise HTTPException(422, "Pick a start date from today onwards and an end date after it")
    if (body.end - body.start).days >= MAX_AWAY_DAYS:
        raise HTTPException(422, f"You can mark at most {MAX_AWAY_DAYS} days at a time")
    now, marked, gained = clock.utcnow(), 0, 0
    day = body.start
    while day <= body.end:
        for meal in MEALS:
            if now < cutoff_utc(day, meal, tenant.timezone):
                gained += _set_notice(db, tenant, user, day, meal, "skip", today)
                marked += 1
        day += timedelta(days=1)
    db.commit()
    return {"marked": marked, "gained": gained, "points": user.points}


@router.post("/meals/{day}/{meal}/ratings")
def rate(
    day: date,
    meal: str,
    body: RatingsBody,
    user: User = Depends(resident),
    tenant: Tenant = Depends(kitchen_of),
    db: Session = Depends(get_db),
) -> dict:
    check_meal(meal)
    today = clock.local_today(tenant.timezone)
    if day < today - timedelta(days=1) or clock.utcnow() < window_utc(day, meal, tenant.timezone)[0]:
        raise HTTPException(409, "You can rate a meal from when it is served until the next day")
    on_menu = {
        row.dish_id: row
        for row in db.scalars(select(DishService).where(DishService.tenant_id == tenant.id, DishService.day == day, DishService.meal == meal))
    }
    for item in body.ratings:
        if item.dish_id not in on_menu:
            raise HTTPException(422, "One of those dishes was not on this menu")
        existing = db.scalar(
            select(Rating).where(Rating.tenant_id == tenant.id, Rating.user_id == user.id, Rating.day == day, Rating.meal == meal, Rating.dish_id == item.dish_id)
        )
        tally = on_menu[item.dish_id]
        if existing is None:
            db.add(Rating(tenant_id=tenant.id, user_id=user.id, day=day, meal=meal, dish_id=item.dish_id, stars=item.stars, portion=item.portion, created_at=clock.utcnow()))
            tally.rating_sum, tally.rating_n = tally.rating_sum + item.stars, tally.rating_n + 1
        else:
            tally.rating_sum += item.stars - existing.stars
            existing.stars, existing.portion = item.stars, item.portion
    gained = points.award(db, user, "rating", f"{day.isoformat()}:{meal}", points.RATING_POINTS, today)
    db.commit()
    return {"gained": gained, "points": user.points, "streak": user.streak}


@router.post("/games/score")
def game_score(
    body: ScoreBody, user: User = Depends(resident), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)
) -> dict:
    today = clock.local_today(tenant.timezone)
    played = points.game_plays_today(db, user, body.game, today)
    earned = points.game_points(body.game, body.score) if played < points.GAME_PLAYS_PER_DAY else 0
    gained = points.award(db, user, "game", f"{today.isoformat()}:{body.game}:{played + 1}", earned, today) if earned else 0
    db.add(GameScore(tenant_id=tenant.id, user_id=user.id, game=body.game, score=body.score, points=gained, created_at=clock.utcnow()))
    best = db.scalar(select(func.max(GameScore.score)).where(GameScore.user_id == user.id, GameScore.game == body.game)) or 0
    db.commit()
    return {
        "gained": gained,
        "points": user.points,
        "best": max(int(best), body.score),
        "scored_plays_left": max(points.GAME_PLAYS_PER_DAY - played - (1 if gained else 0), 0),
    }


def _short(name: str) -> str:
    first, _, rest = name.partition(" ")
    return f"{first} {rest[:1]}." if rest else first


@router.get("/leaderboard")
def leaderboard(user: User = Depends(resident), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    top = db.scalars(
        select(User).where(User.tenant_id == tenant.id, User.role == "student").order_by(User.points.desc(), User.id).limit(20)
    ).all()
    rows = [
        {"rank": index + 1, "name": u.name if u.id == user.id else _short(u.name), "block": u.room[:1], "points": u.points, "streak": u.streak, "me": u.id == user.id}
        for index, u in enumerate(top)
    ]
    my_rank = points.rank_of(db, user)
    if not any(row["me"] for row in rows):
        rows.append({"rank": my_rank, "name": user.name, "block": user.room[:1], "points": user.points, "streak": user.streak, "me": True})
    return {"rows": rows, "me": {"rank": my_rank, "points": user.points, "streak": user.streak}, "residents": tenant.strength}


@router.get("/me/summary")
def my_summary(user: User = Depends(resident), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    today = clock.local_today(tenant.timezone)
    events = db.scalars(select(PointEvent).where(PointEvent.user_id == user.id).order_by(PointEvent.created_at.desc()).limit(12)).all()
    notices = db.scalar(
        select(func.count()).select_from(PointEvent).where(PointEvent.user_id == user.id, PointEvent.reason == "skip")
    ) or 0
    return {
        "rank": points.rank_of(db, user),
        "residents": tenant.strength,
        "points": user.points,
        "streak": user.streak,
        "notices": int(notices),
        "plates_saved_kg": round(int(notices) * 0.45, 1),
        "events": [{"reason": e.reason, "ref": e.ref, "points": e.points, "at": clock.iso_utc(e.created_at)} for e in events],
        "today": today.isoformat(),
    }
