"""Builds the demo hostel: eighteen weeks of history replayed week by week.

    python -m katori.seed            create the demo if the database is empty
    python -m katori.seed --reset    wipe everything and build it again

The replay follows how a mess would really adopt Katori:
  weeks 1-4    the kitchen only measures (head counts, weights) and cooks by habit
  weeks 5-12   models are trained weekly and advise in the background ("shadow")
  weeks 13-18  the kitchen cooks from the sheet
so every forecast in the history was made by a model that had not seen that day.
"""

from __future__ import annotations

import argparse
import os
import secrets
import time
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from .catalog import DISHES, WEEKLY_CHART, co2_per_kg
from .config import get_settings
from .db import Base, SessionLocal, engine, init_db
from .meals import MEALS, window_utc
from .ml import pipeline, registry
from .models import Dish, MealService, MenuTemplate, PointEvent, Tenant, User, WaitSample
from .security import NO_LOGIN, hash_password
from .sim import world
from .sim.engine import Kitchen, catch_up, ensure_day

DEMO_SLUG = "nilgiri"
DEMO_EMAILS = {
    "manager": "manager@nilgiri.katori.demo",
    "kitchen": "kitchen@nilgiri.katori.demo",
    "student": "student@nilgiri.katori.demo",
}
_FIRST = (
    "Aarav Aditi Akash Ananya Arjun Bhavya Chirag Deepak Divya Esha Farhan Gaurav Harsh Isha Jatin Kavya Kunal "
    "Lakshay Manish Meenal Naveen Neha Nikhil Pooja Pranav Priya Rahul Riya Rohan Sakshi Sameer Sanya Shivam "
    "Sneha Tanvi Tushar Utkarsh Varun Vidhi Yash"
).split()
_LAST = (
    "Agarwal Bansal Chauhan Dubey Fernandes Gupta Iyer Jain Kapoor Khan Kulkarni Malhotra Mehta Mishra Nair "
    "Pandey Patel Rao Reddy Saxena Sharma Sinha Thakur Verma Yadav"
).split()


def _demo_password() -> str:
    # The demo signs people in with one click; a password only exists if the operator sets one.
    return hash_password(os.environ.get("KATORI_DEMO_PASSWORD") or secrets.token_urlsafe(24))


def _create_kitchen(db: Session, strength: int, seed: int) -> Tenant:
    tenant = Tenant(
        slug=DEMO_SLUG, name="Nilgiri Hostel", kind="hostel", city="Jaipur", strength=strength,
        is_demo=True, sim_seed=seed, created_at=clock.utcnow(),
    )  # fmt: skip
    db.add(tenant)
    db.flush()

    password = _demo_password()
    db.add_all(
        [
            User(tenant_id=tenant.id, email=DEMO_EMAILS["manager"], name="Meera Nair", role="manager",
                 password_hash=password, is_demo=True),
            User(tenant_id=tenant.id, email=DEMO_EMAILS["kitchen"], name="Ramesh Yadav", role="kitchen",
                 password_hash=password, is_demo=True),
            User(tenant_id=tenant.id, email=DEMO_EMAILS["student"], name="Gangadhar Singh", role="student",
                 password_hash=password, room="B-214", diet="veg", points=118, streak=9, is_demo=True),
        ]
    )  # fmt: skip
    rng = world.rng_for(seed, "residents")
    for index in range(strength - 1):
        block, room = "ABCD"[index % 4], 101 + (index // 4) % 30 + 100 * ((index // 120) % 3)
        db.add(
            User(
                tenant_id=tenant.id,
                email=f"resident{index + 1:03d}@nilgiri.katori.demo",
                name=f"{_FIRST[int(rng.integers(len(_FIRST)))]} {_LAST[int(rng.integers(len(_LAST)))]}",
                role="student",
                password_hash=NO_LOGIN,
                room=f"{block}-{room}",
                diet="veg" if rng.random() < 0.45 else "nonveg",
                points=int(rng.gamma(2.0, 30.0)),
                streak=min(int(rng.geometric(0.11)), 45),
                is_sim=True,
            )
        )

    load_starter_menu(db, tenant)
    return tenant


def load_starter_menu(db: Session, tenant: Tenant) -> None:
    """Give a kitchen the starter dish list and weekly food chart; both are meant to be edited afterwards."""
    by_name: dict[str, Dish] = {}
    for spec in DISHES:
        dish = Dish(
            tenant_id=tenant.id, name=spec.name, category=spec.category, veg=spec.veg, portion_g=spec.portion_g,
            piece_g=spec.piece_g, cost_per_kg=spec.cost_per_kg, co2_per_kg=co2_per_kg(spec), slow=spec.slow,
            ingredients=[{"name": name, "g_per_kg": grams} for name, grams in spec.ingredients],
        )  # fmt: skip
        db.add(dish)
        by_name[spec.name] = dish
    db.flush()
    for weekday, chart in enumerate(WEEKLY_CHART):
        for meal in MEALS:
            for position, name in enumerate(chart[meal]):
                db.add(
                    MenuTemplate(
                        tenant_id=tenant.id, weekday=weekday, meal=meal, dish_id=by_name[name].id, position=position
                    )
                )
    db.flush()


def _record_waits(db: Session, tenant: Tenant, kitchen: Kitchen, days: int) -> None:
    """Replay the serving line of recent sittings so the wait-time model has finished waits to learn from."""
    today = clock.local_today(tenant.timezone)
    services = db.scalars(
        select(MealService).where(
            MealService.tenant_id == tenant.id,
            MealService.day >= today - timedelta(days=days),
            MealService.served.is_not(None),
        )
    )
    for service in services:
        rng = world.rng_for(tenant.sim_seed, "counters", service.day.isoformat(), service.meal)
        counters = 3 if service.served > 230 and rng.random() < 0.5 else 2
        slow = sum(1 for d in kitchen.menu(service.day, service.meal) if d.slow)
        start, end = window_utc(service.day, service.meal, tenant.timezone)
        waits = world.simulate_line(
            tenant.sim_seed, service.day, service.meal, service.served, counters, slow, (end - start).total_seconds() / 60
        )
        step = max(len(waits) // 70, 1)
        for minute, ahead, wait_s in waits[::step]:
            db.add(
                WaitSample(
                    tenant_id=tenant.id, day=service.day, meal=service.meal, minute=round(minute, 1), ahead=ahead,
                    counters=counters, slow_dishes=slow, wait_s=round(wait_s, 1),
                )
            )  # fmt: skip
    db.flush()


def _demo_resident_history(db: Session, tenant: Tenant) -> None:
    """A believable points ledger for the demo resident (totals 118, matching the account)."""
    student = db.scalar(select(User).where(User.email == DEMO_EMAILS["student"]))
    today = clock.local_today(tenant.timezone)
    ledger = [
        (1, "skip", "dinner", 5), (2, "rating", "lunch", 2), (2, "game", "bin-it", 14), (3, "skip", "breakfast", 5),
        (4, "rating", "dinner", 2), (5, "skip", "dinner", 5), (5, "game", "just-enough", 18), (6, "rating", "lunch", 2),
        (7, "streak", "week", 20), (8, "skip", "breakfast", 5), (9, "game", "bin-it", 16), (10, "rating", "dinner", 2),
        (11, "skip", "snacks", 5), (12, "game", "just-enough", 12), (13, "skip", "dinner", 5),
    ]  # fmt: skip
    for days_ago, reason, what, points in ledger:
        when = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=14)
        ref = f"{(today - timedelta(days=days_ago)).isoformat()}:{what}"
        db.add(PointEvent(tenant_id=tenant.id, user_id=student.id, reason=reason, ref=ref, points=points, created_at=when))
    db.flush()


def seed_demo(
    db: Session,
    *,
    now: datetime | None = None,
    history_days: int = 126,
    live_days: int = 42,
    strength: int = 420,
    seed: int | None = None,
    quick: bool = False,
    log=lambda message: None,
) -> Tenant:
    now = now or clock.utcnow()
    seed = get_settings().sim_seed if seed is None else seed
    tenant = _create_kitchen(db, strength, seed)
    today = clock.to_local(now, tenant.timezone).date()
    first_day = today - timedelta(days=history_days)
    tenant.katori_since = today - timedelta(days=live_days)

    kitchen = Kitchen(db, tenant)
    for offset in range(history_days):
        ensure_day(kitchen, first_day + timedelta(days=offset), substitute=True)
    db.flush()

    cursor, yesterday = first_day, today - timedelta(days=1)
    while cursor <= yesterday:
        week_end = min(cursor + timedelta(days=6), yesterday)
        moment = window_utc(week_end, "dinner", tenant.timezone)[1]
        catch_up(db, tenant, moment, live=False)
        logged_days = (week_end - first_day).days + 1
        if logged_days >= pipeline.MIN_HISTORY_DAYS and week_end < yesterday:
            runs = pipeline.train_all(db, tenant, quick=True, note="weekly retrain", at=moment)
            log(f"  week ending {week_end}: " + ", ".join(f"{r.kind}={r.metrics.get('mae')} ({r.status})" for r in runs))
        cursor = week_end + timedelta(days=1)

    _record_waits(db, tenant, kitchen, days=21)
    runs = pipeline.train_all(db, tenant, quick=quick, note="nightly retrain", at=now)
    for run in runs:
        log(f"  final {run.kind}: {run.algorithm} mae={run.metrics.get('mae')} baseline={run.metrics.get('baseline_mae')} ({run.status})")
    _demo_resident_history(db, tenant)
    catch_up(db, tenant, now, live=True)
    db.flush()
    return tenant


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Katori demo hostel")
    parser.add_argument("--reset", action="store_true", help="drop all data first")
    parser.add_argument("--quick", action="store_true", help="lighter final training (for tests and CI)")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
        registry.forget_cache()
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(Tenant).where(Tenant.slug == DEMO_SLUG)):
            print("Demo hostel already exists. Use --reset to rebuild it.")
            return
        started = time.perf_counter()
        print("Replaying 18 weeks of Nilgiri Hostel...")
        tenant = seed_demo(db, quick=args.quick, log=print)
        db.commit()
        sittings = db.scalars(select(MealService).where(MealService.tenant_id == tenant.id)).all()
        done = [s for s in sittings if s.served is not None]
        print(f"Done in {time.perf_counter() - started:.1f}s: {len(done)} sittings logged, {len(sittings) - len(done)} planned ahead.")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
