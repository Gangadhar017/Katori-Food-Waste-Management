"""The kitchen's two jobs in Katori: read the cook sheet before a meal, log the weights after it."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..db import get_db
from ..meals import MEAL_INDEX, cutoff_utc, iter_slots, last_finished, window_utc
from ..ml.headcount import LABELS
from ..ml.pipeline import is_frozen
from ..models import CalendarDay, Dish, DishService, MealService, MenuEntry, Tenant, User
from ..security import require_role
from ..services import analytics
from .deps import check_meal, kitchen_of, sitting_state

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"])
staff = require_role("kitchen", "manager")


class DishLog(BaseModel):
    dish_id: int
    prepared_kg: float = Field(ge=0, le=2000)
    leftover_kg: float = Field(ge=0, le=2000)
    ran_out: bool = False
    short_heads: int = Field(default=0, ge=0, le=5000)


class SittingLog(BaseModel):
    served: int = Field(ge=0, le=5000)
    prep_waste_kg: float = Field(ge=0, le=500)
    plate_waste_kg: float = Field(ge=0, le=500)
    dishes: list[DishLog] = Field(min_length=1, max_length=20)


def _service(db: Session, tenant: Tenant, day: date, meal: str) -> MealService:
    service = db.scalar(select(MealService).where(MealService.tenant_id == tenant.id, MealService.day == day, MealService.meal == meal))
    if service is None:
        raise HTTPException(404, "That sitting is not on the chart")
    return service


def _menu_rows(db: Session, tenant: Tenant, day: date, meal: str) -> list[tuple[Dish, DishService | None]]:
    rows = {r.dish_id: r for r in db.scalars(select(DishService).where(DishService.tenant_id == tenant.id, DishService.day == day, DishService.meal == meal))}
    dishes = db.scalars(
        select(Dish).join(MenuEntry, MenuEntry.dish_id == Dish.id)
        .where(MenuEntry.tenant_id == tenant.id, MenuEntry.day == day, MenuEntry.meal == meal)
        .order_by(MenuEntry.position)
    )  # fmt: skip
    return [(dish, rows.get(dish.id)) for dish in dishes]


def _model_label(service: MealService) -> str:
    name = service.forecast_model.partition(":")[2].partition("#")[0]
    return LABELS.get(name, "Starting estimate" if name == "cold-start" else name)


@router.get("/sheet")
def cook_sheet(
    day: date | None = None,
    meal: str | None = None,
    _: User = Depends(staff),
    tenant: Tenant = Depends(kitchen_of),
    db: Session = Depends(get_db),
) -> dict:
    """How many to expect and how much of each dish to cook for one sitting."""
    now = clock.utcnow()
    today = clock.local_today(tenant.timezone)
    ahead = [
        (d, m)
        for d, m in iter_slots(today, today + timedelta(days=2))
        if window_utc(d, m, tenant.timezone)[1] > now
    ][:8]
    if day is None or meal is None:
        day, meal = ahead[0]
    check_meal(meal)
    service = _service(db, tenant, day, meal)
    marked = db.scalar(select(CalendarDay).where(CalendarDay.tenant_id == tenant.id, CalendarDay.day == day))
    last_week = db.scalar(
        select(MealService.served).where(MealService.tenant_id == tenant.id, MealService.day == day - timedelta(days=7), MealService.meal == meal)
    )
    expected = service.forecast_p50
    dishes, advised_total, rule_total, saving_cost = [], 0.0, 0.0, 0.0
    for dish, row in _menu_rows(db, tenant, day, meal):
        advised = row.recommended_kg if row else None
        rule = row.habit_kg if row else None
        if advised is not None and rule is not None:
            advised_total, rule_total = advised_total + advised, rule_total + rule
            saving_cost += (rule - advised) * dish.cost_per_kg
        dishes.append(
            {
                "dish_id": dish.id,
                "name": dish.name,
                "category": dish.category,
                "veg": dish.veg,
                "advised_kg": advised,
                "rule_kg": rule,
                "pieces": round(advised * 1000 / dish.piece_g) if advised is not None and dish.piece_g else None,
                "per_head_g": round(advised * 1000 / expected) if advised is not None and expected else None,
                "standard_g": dish.portion_g,
                "ingredients": [
                    {"name": item["name"], "kg": round(advised * item["g_per_kg"] / 1000, 1)} for item in (dish.ingredients or [])
                ]
                if advised is not None
                else [],
            }
        )
    start, _end = window_utc(day, meal, tenant.timezone)
    return {
        "day": day.isoformat(),
        "meal": meal,
        "state": sitting_state(now, day, meal, tenant.timezone),
        "starts_at": clock.iso_utc(start),
        "cutoff_at": clock.iso_utc(cutoff_utc(day, meal, tenant.timezone)),
        "final": is_frozen(service),
        "calendar": {"kind": marked.kind, "label": marked.label} if marked else None,
        "headcount": {
            "expected": round(expected) if expected is not None else None,
            "low": round(service.forecast_p10) if service.forecast_p10 is not None else None,
            "high": round(service.forecast_p90) if service.forecast_p90 is not None else None,
            "roll": tenant.strength,
            "notices": service.skips,
            "model": _model_label(service) if service.forecast_model else None,
            "last_week": last_week,
        },
        "dishes": dishes,
        "totals": {
            "advised_kg": round(advised_total, 1),
            "rule_kg": round(rule_total, 1),
            "saving_kg": round(rule_total - advised_total, 1),
            "saving_cost": round(saving_cost),
        },
        "service_level": tenant.service_level,
        "sittings": [{"day": d.isoformat(), "meal": m} for d, m in ahead],
    }


def _log_out(db: Session, tenant: Tenant, service: MealService) -> dict:
    return {
        "day": service.day.isoformat(),
        "meal": service.meal,
        "logged": service.served is not None,
        "logged_by": service.logged_by,
        "logged_at": clock.iso_utc(service.logged_at),
        "served": service.served,
        "expected": round(service.forecast_p50) if service.forecast_p50 is not None else None,
        "prep_waste_kg": service.prep_waste_kg,
        "plate_waste_kg": service.plate_waste_kg,
        "dishes": [
            {
                "dish_id": dish.id,
                "name": dish.name,
                "category": dish.category,
                "veg": dish.veg,
                "advised_kg": row.recommended_kg if row else None,
                "prepared_kg": row.prepared_kg if row else None,
                "leftover_kg": row.leftover_kg if row else None,
                "ran_out": bool(row.ran_out) if row else False,
                "short_heads": row.short_heads if row else 0,
            }
            for dish, row in _menu_rows(db, tenant, service.day, service.meal)
        ],
    }


@router.get("/log")
def get_log(
    day: date | None = None,
    meal: str | None = None,
    _: User = Depends(staff),
    tenant: Tenant = Depends(kitchen_of),
    db: Session = Depends(get_db),
) -> dict:
    """The weights logged for a sitting (by default the one that just finished)."""
    now = clock.utcnow()
    today = clock.local_today(tenant.timezone)
    finished = [
        (d, m) for d, m in iter_slots(today - timedelta(days=2), today) if window_utc(d, m, tenant.timezone)[0] <= now
    ]
    finished.sort(key=lambda slot: (slot[0], MEAL_INDEX[slot[1]]), reverse=True)
    if day is None or meal is None:
        day, meal = last_finished(now, tenant.timezone)
    check_meal(meal)
    return {**_log_out(db, tenant, _service(db, tenant, day, meal)), "sittings": [{"day": d.isoformat(), "meal": m} for d, m in finished[:8]]}


@router.put("/log/{day}/{meal}")
def put_log(
    day: date,
    meal: str,
    body: SittingLog,
    _: User = Depends(staff),
    tenant: Tenant = Depends(kitchen_of),
    db: Session = Depends(get_db),
) -> dict:
    check_meal(meal)
    service = _service(db, tenant, day, meal)
    if clock.utcnow() < window_utc(day, meal, tenant.timezone)[0]:
        raise HTTPException(409, "This sitting has not been served yet")
    menu = dict(_menu_rows(db, tenant, day, meal))
    by_id = {dish.id: dish for dish in menu}
    if {item.dish_id for item in body.dishes} - set(by_id):
        raise HTTPException(422, "One of those dishes was not on this menu")
    for item in body.dishes:
        if item.leftover_kg > item.prepared_kg + 1e-6:
            raise HTTPException(422, f"{by_id[item.dish_id].name}: more left over than was cooked")
        row = menu[by_id[item.dish_id]]
        if row is None:
            row = DishService(tenant_id=tenant.id, day=day, meal=meal, dish_id=item.dish_id)
            db.add(row)
        row.prepared_kg, row.leftover_kg = round(item.prepared_kg, 2), round(item.leftover_kg, 2)
        row.ran_out = item.ran_out and item.leftover_kg == 0
        row.short_heads = min(item.short_heads, body.served) if row.ran_out else 0
    service.served = body.served
    service.prep_waste_kg, service.plate_waste_kg = round(body.prep_waste_kg, 2), round(body.plate_waste_kg, 2)
    service.logged_at, service.logged_by = clock.utcnow(), "kitchen"
    service.mode = "katori" if tenant.katori_since and day >= tenant.katori_since else "habit"
    db.commit()
    analytics.forget_cache()
    return _log_out(db, tenant, service)
