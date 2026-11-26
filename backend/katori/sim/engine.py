"""Keeps a kitchen's days moving.

For every kitchen this lays out upcoming days from the weekly chart and asks the planner
for forecasts. For the demo kitchen it also plays the part of the hostel: once a sitting's
window has closed, the simulator decides what happened and logs it the way staff would.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import groupby

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import clock
from ..meals import MEAL_INDEX, MEALS, cutoff_utc, window_utc
from ..ml.pipeline import Planner, is_frozen, standard_kg, upcoming_services
from ..models import CalendarDay, Dish, DishService, MealService, MenuEntry, MenuTemplate, Rsvp, Tenant, User
from . import world

HORIZON_DAYS = 7
RSVP_KEEP_DAYS = 3


def dish_facts(dish: Dish) -> world.DishFacts:
    return world.DishFacts(dish.name, dish.category, dish.veg, dish.portion_g, dish.slow)


class Kitchen:
    """A kitchen's dishes and weekly chart, loaded once per pass."""

    def __init__(self, db: Session, tenant: Tenant):
        self.db = db
        self.tenant = tenant
        self.dishes = {d.id: d for d in db.scalars(select(Dish).where(Dish.tenant_id == tenant.id))}
        self.by_name = {d.name: d for d in self.dishes.values()}
        self.chart: dict[int, dict[str, list[int]]] = {wd: {meal: [] for meal in MEALS} for wd in range(7)}
        for row in db.scalars(
            select(MenuTemplate).where(MenuTemplate.tenant_id == tenant.id).order_by(MenuTemplate.position)
        ):
            self.chart[row.weekday][row.meal].append(row.dish_id)
        self._residents: list[int] | None = None

    @property
    def simulated(self) -> bool:
        return self.tenant.sim_seed is not None

    def sim_residents(self) -> list[int]:
        if self._residents is None:
            self._residents = list(
                self.db.scalars(
                    select(User.id).where(User.tenant_id == self.tenant.id, User.is_sim.is_(True)).order_by(User.id)
                )
            )
        return self._residents

    def menu(self, day: date, meal: str) -> list[Dish]:
        return [
            self.dishes[dish_id]
            for dish_id in self.db.scalars(
                select(MenuEntry.dish_id)
                .where(MenuEntry.tenant_id == self.tenant.id, MenuEntry.day == day, MenuEntry.meal == meal)
                .order_by(MenuEntry.position)
            )
        ]

    def truth(self, day: date, meal: str) -> world.MealTruth:
        facts = [dish_facts(d) for d in self.menu(day, meal)]
        context = world.day_context(self.tenant.sim_seed, day)
        return world.meal_truth(self.tenant.sim_seed, day, meal, facts, context, self.tenant.strength)


def write_menu(kitchen: Kitchen, day: date, *, substitute: bool = False) -> None:
    """Put the weekly chart's dishes on this day, with the quantity the old fixed rule would cook."""
    tenant, db = kitchen.tenant, kitchen.db
    names = {meal: [kitchen.dishes[i].name for i in ids] for meal, ids in kitchen.chart[day.weekday()].items()}
    context = world.day_context(tenant.sim_seed, day) if kitchen.simulated else None
    if substitute and kitchen.simulated:
        names = world.menu_with_swaps(tenant.sim_seed, day, names)
    for meal, meal_names in names.items():
        dishes = [kitchen.by_name[name] for name in meal_names if name in kitchen.by_name]
        facts = [dish_facts(d) for d in dishes]
        for position, dish in enumerate(dishes):
            db.add(MenuEntry(tenant_id=tenant.id, day=day, meal=meal, dish_id=dish.id, position=position))
            if context is not None:
                habit = world.habit_kg(facts[position], facts, meal, tenant.strength, context)
            else:
                habit = standard_kg(dish.portion_g, meal, tenant.strength)
            db.add(DishService(tenant_id=tenant.id, day=day, meal=meal, dish_id=dish.id, habit_kg=habit))


def ensure_day(kitchen: Kitchen, day: date, *, substitute: bool = False) -> bool:
    """Create the day's four sittings and menu if they do not exist yet."""
    tenant, db = kitchen.tenant, kitchen.db
    exists = db.scalar(select(MealService.id).where(MealService.tenant_id == tenant.id, MealService.day == day).limit(1))
    if exists:
        return False
    marked = db.scalar(select(CalendarDay).where(CalendarDay.tenant_id == tenant.id, CalendarDay.day == day))
    kind, temp, rain = (marked.kind if marked else ""), 25.0, 0.0
    if kitchen.simulated:
        context = world.day_context(tenant.sim_seed, day)
        kind, temp, rain = context.kind, context.temp_c, context.rain_mm
        if kind and marked is None:
            db.add(CalendarDay(tenant_id=tenant.id, day=day, kind=kind, label=context.label))
    for meal in MEALS:
        db.add(MealService(tenant_id=tenant.id, day=day, meal=meal, calendar_kind=kind, temp_c=temp, rain_mm=rain))
    write_menu(kitchen, day, substitute=substitute)
    return True


def count_skips(db: Session, tenant_id: int, day: date, meal: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Rsvp)
            .where(Rsvp.tenant_id == tenant_id, Rsvp.day == day, Rsvp.meal == meal, Rsvp.status == "skip")
        )
        or 0
    )


def complete_sitting(kitchen: Kitchen, service: MealService) -> None:
    """Simulator only: decide what happened at a finished sitting and log it."""
    tenant, db = kitchen.tenant, kitchen.db
    seed = tenant.sim_seed
    dishes = kitchen.menu(service.day, service.meal)
    facts = [dish_facts(d) for d in dishes]
    context = world.day_context(seed, service.day)
    truth = world.meal_truth(seed, service.day, service.meal, facts, context, tenant.strength)
    rows = {
        row.dish_id: row
        for row in db.scalars(
            select(DishService).where(
                DishService.tenant_id == tenant.id, DishService.day == service.day, DishService.meal == service.meal
            )
        )
    }
    live = tenant.katori_since is not None and service.day >= tenant.katori_since
    rng = world.rng_for(seed, "cook", service.day.isoformat(), service.meal)
    prepared: dict[str, float] = {}
    followed_sheet = False
    for dish, fact in zip(dishes, facts, strict=True):
        row = rows.get(dish.id)
        if row is None:
            row = DishService(tenant_id=tenant.id, day=service.day, meal=service.meal, dish_id=dish.id)
            db.add(row)
        if row.habit_kg is None:
            row.habit_kg = world.habit_kg(fact, facts, service.meal, tenant.strength, context)
        if live and row.recommended_kg:
            # Cooks follow the sheet, give or take a ladle.
            row.prepared_kg = max(round(row.recommended_kg * float(rng.normal(1.0, 0.015)), 1), 0.1)
            followed_sheet = True
        else:
            row.prepared_kg = row.habit_kg
        wanted = truth.demand_kg.get(dish.name, 0.0)
        row.ran_out = wanted > row.prepared_kg * 1.01
        row.leftover_kg = round(max(row.prepared_kg - wanted, 0.0), 2)
        row.short_heads = 0
        if row.ran_out and wanted > 0:
            # Staff note roughly how many people reached an empty pot.
            missed = (wanted - row.prepared_kg) / wanted * truth.served * float(rng.normal(1.0, 0.2))
            row.short_heads = int(min(max(round(missed), 1), truth.served))
        stars, votes = truth.ratings.get(dish.name, (0.0, 0))
        row.rating_sum, row.rating_n = stars, votes
        prepared[dish.name] = row.prepared_kg
    service.mode = "katori" if followed_sheet else "habit"
    service.served = truth.served
    service.prep_waste_kg = world.prep_waste_kg(seed, service.day, service.meal, prepared, facts)
    service.plate_waste_kg = truth.plate_waste_kg
    service.logged_at = window_utc(service.day, service.meal, tenant.timezone)[1]
    service.logged_by = "simulator"


def refresh_rsvps(kitchen: Kitchen, now: datetime) -> None:
    """Simulator only: residents file their skip notices as each cut-off approaches."""
    tenant, db = kitchen.tenant, kitchen.db
    residents = kitchen.sim_residents()
    sim_ids = select(User.id).where(User.tenant_id == tenant.id, User.is_sim.is_(True))
    for service in upcoming_services(db, tenant):
        hours = (cutoff_utc(service.day, service.meal, tenant.timezone) - now).total_seconds() / 3600
        if hours > 30:
            continue
        final = kitchen.truth(service.day, service.meal).skips
        target = min(final if hours <= 0 else world.skips_declared_by(final, hours), len(residents))
        have = int(
            db.scalar(
                select(func.count())
                .select_from(Rsvp)
                .where(
                    Rsvp.tenant_id == tenant.id,
                    Rsvp.day == service.day,
                    Rsvp.meal == service.meal,
                    Rsvp.user_id.in_(sim_ids),
                )
            )
            or 0
        )
        if target > have:
            order = world.rng_for(tenant.sim_seed, "notice", service.day.isoformat(), service.meal).permutation(
                len(residents)
            )
            for index in order[have:target]:
                db.add(
                    Rsvp(
                        tenant_id=tenant.id, user_id=residents[int(index)], day=service.day, meal=service.meal,
                        status="skip", updated_at=now,
                    )
                )  # fmt: skip
            db.flush()
        if not is_frozen(service):
            service.skips = count_skips(db, tenant.id, service.day, service.meal)
    today = clock.to_local(now, tenant.timezone).date()
    db.execute(
        delete(Rsvp).where(
            Rsvp.tenant_id == tenant.id, Rsvp.day < today - timedelta(days=RSVP_KEEP_DAYS), Rsvp.user_id.in_(sim_ids)
        )
    )


def catch_up(db: Session, tenant: Tenant, now: datetime | None = None, *, live: bool = True) -> dict:
    """Bring a kitchen up to `now`: lay out days ahead, close finished sittings, refresh forecasts.

    `live=False` is used while replaying history: it skips the parts that only matter in real time.
    """
    now = now or clock.utcnow()
    kitchen = Kitchen(db, tenant)
    today = clock.to_local(now, tenant.timezone).date()
    last = db.scalar(select(func.max(MealService.day)).where(MealService.tenant_id == tenant.id))
    day = last + timedelta(days=1) if last else today
    while day <= today + timedelta(days=HORIZON_DAYS):
        ensure_day(kitchen, day)
        day += timedelta(days=1)
    db.flush()

    planner = Planner(db, tenant)
    completed = 0
    if kitchen.simulated:
        finished = [
            s for s in upcoming_services(db, tenant) if window_utc(s.day, s.meal, tenant.timezone)[1] <= now
        ]
        finished.sort(key=lambda s: (s.day, MEAL_INDEX[s.meal]))
        for _, sittings in groupby(finished, key=lambda s: s.day):
            sittings = list(sittings)
            for service in sittings:
                if not is_frozen(service):
                    declared = count_skips(db, tenant.id, service.day, service.meal)
                    service.skips = max(declared, kitchen.truth(service.day, service.meal).skips)
            db.flush()
            planner.plan(sittings, now=now, allow_cold=False)
            for service in sittings:
                complete_sitting(kitchen, service)
            completed += len(sittings)
            db.flush()
        if live:
            refresh_rsvps(kitchen, now)
            db.flush()

    planned = 0
    if live:
        if not kitchen.simulated:
            for service in upcoming_services(db, tenant):
                if not is_frozen(service):
                    service.skips = count_skips(db, tenant.id, service.day, service.meal)
        todo = [
            s
            for s in upcoming_services(db, tenant)
            if s.forecast_p50 is None or (now >= cutoff_utc(s.day, s.meal, tenant.timezone) and not is_frozen(s))
        ]
        planned = planner.plan(todo, now=now)
    return {"completed": completed, "planned": planned}


def rebuild_future_menu(db: Session, tenant: Tenant, now: datetime | None = None) -> int:
    """After the weekly chart changes: rewrite the menu of every day that has not started cooking."""
    now = now or clock.utcnow()
    kitchen = Kitchen(db, tenant)
    today = clock.to_local(now, tenant.timezone).date()
    days = sorted(
        set(
            db.scalars(
                select(MealService.day).where(MealService.tenant_id == tenant.id, MealService.day > today).distinct()
            )
        )
    )
    if not days:
        return 0
    db.execute(delete(MenuEntry).where(MenuEntry.tenant_id == tenant.id, MenuEntry.day.in_(days)))
    db.execute(delete(DishService).where(DishService.tenant_id == tenant.id, DishService.day.in_(days)))
    for service in db.scalars(select(MealService).where(MealService.tenant_id == tenant.id, MealService.day.in_(days))):
        service.forecast_p10 = service.forecast_p50 = service.forecast_p90 = None
        service.forecast_model, service.forecast_at = "", None
    db.flush()
    for day in days:
        write_menu(kitchen, day)
    db.flush()
    Planner(db, tenant).plan(upcoming_services(db, tenant), now=now)
    return len(days)
