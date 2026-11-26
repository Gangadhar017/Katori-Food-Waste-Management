"""Shared request dependencies and the small serialisers every router uses."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .. import clock
from ..db import get_db
from ..meals import MEALS, cutoff_utc, window_utc
from ..models import Dish, Tenant, User
from ..security import current_user
from ..services import upkeep


def kitchen_of(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Tenant:
    """The signed-in user's kitchen, brought up to date first."""
    tenant = db.get(Tenant, user.tenant_id)
    upkeep.tick(db, tenant)
    return tenant


def check_meal(meal: str) -> str:
    if meal not in MEALS:
        raise HTTPException(404, "Unknown meal")
    return meal


def sitting_state(now: datetime, day: date, meal: str, tz: str) -> str:
    """open (notice still counts) -> cooking -> serving -> done"""
    start, end = window_utc(day, meal, tz)
    if now >= end:
        return "done"
    if now >= start:
        return "serving"
    if now >= cutoff_utc(day, meal, tz):
        return "cooking"
    return "open"


def tenant_out(tenant: Tenant) -> dict:
    return {
        "slug": tenant.slug,
        "name": tenant.name,
        "city": tenant.city,
        "kind": tenant.kind,
        "strength": tenant.strength,
        "service_level": tenant.service_level,
        "counters_open": tenant.counters_open,
        "katori_since": tenant.katori_since.isoformat() if tenant.katori_since else None,
        "is_demo": tenant.is_demo,
        "simulated": tenant.sim_seed is not None,
        "today": clock.local_today(tenant.timezone).isoformat(),
        "timezone": tenant.timezone,
    }


def user_out(user: User, tenant: Tenant) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "room": user.room,
        "diet": user.diet,
        "points": user.points,
        "streak": user.streak,
        "tenant": tenant_out(tenant),
    }


def dish_out(dish: Dish) -> dict:
    return {"id": dish.id, "name": dish.name, "category": dish.category, "veg": dish.veg, "slow": dish.slow}
