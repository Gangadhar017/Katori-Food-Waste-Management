"""The serving line: digital tokens, live position, wait estimates.

In a real mess the counter staff move the line ("next"). In demo mode a simulated crowd
keeps joining and being served, so a visitor always finds a line to stand in. The crowd is
advanced lazily, whenever someone looks at the line, so nothing has to run in the background.
"""

from __future__ import annotations

import math
import threading
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import clock
from ..meals import current_or_next, window_utc
from ..ml import registry
from ..ml.waittime import naive_wait
from ..models import Dish, MenuEntry, QueueState, QueueTicket, Tenant, User, WaitSample
from ..sim import world

_lock = threading.Lock()
WARM_UP = timedelta(seconds=240)  # a fresh demo line starts with a few minutes of crowd behind it
STALE_AFTER = timedelta(minutes=8)  # nobody looked for this long: start the crowd afresh
MAX_WAITING = 40
MIN_WAITING = 5
DEMO_PLATE_SECONDS = 18.0  # how long a visitor's own "your turn" lasts in demo mode


def _menu(db: Session, tenant_id: int, day, meal: str) -> list[Dish]:
    return list(
        db.scalars(
            select(Dish)
            .join(MenuEntry, MenuEntry.dish_id == Dish.id)
            .where(MenuEntry.tenant_id == tenant_id, MenuEntry.day == day, MenuEntry.meal == meal)
            .order_by(MenuEntry.position)
        )
    )


def _state(db: Session, tenant: Tenant, now: datetime) -> tuple[QueueState, str]:
    """The line of the sitting that is open now (or opens next); a new sitting starts with an empty line."""
    day, meal, phase = current_or_next(now, tenant.timezone)
    state = db.get(QueueState, tenant.id)
    if state is None:
        state = QueueState(tenant_id=tenant.id, day=day, meal=meal, next_token=1, busy={})
        db.add(state)
    elif (state.day, state.meal) != (day, meal):
        db.execute(delete(QueueTicket).where(QueueTicket.tenant_id == tenant.id))
        state.day, state.meal, state.next_token, state.busy = day, meal, 1, {}
        state.sim_time = state.next_arrival = None
    return state, phase


def _waiting(db: Session, tenant_id: int) -> list[QueueTicket]:
    return list(
        db.scalars(
            select(QueueTicket)
            .where(QueueTicket.tenant_id == tenant_id, QueueTicket.status == "waiting")
            .order_by(QueueTicket.token)
        )
    )


def _issue(db: Session, tenant: Tenant, state: QueueState, when: datetime, user_id: int | None, ahead: int) -> QueueTicket:
    ticket = QueueTicket(
        tenant_id=tenant.id, day=state.day, meal=state.meal, user_id=user_id, token=state.next_token,
        status="waiting", joined_at=when, ahead_at_join=ahead,
    )  # fmt: skip
    state.next_token += 1
    db.add(ticket)
    return ticket


def _call(db: Session, tenant: Tenant, state: QueueState, ticket: QueueTicket, counter: int, when: datetime, slow: int):
    ticket.status, ticket.counter, ticket.called_at = "called", counter, when
    if ticket.user_id is not None:
        # A resident's finished wait is a training example for the wait-time model.
        opened = window_utc(state.day, state.meal, tenant.timezone)[0]
        db.add(
            WaitSample(
                tenant_id=tenant.id, day=state.day, meal=state.meal,
                minute=round(max((ticket.joined_at - opened).total_seconds() / 60, 0.0), 1),
                ahead=ticket.ahead_at_join, counters=tenant.counters_open, slow_dishes=slow,
                wait_s=round((when - ticket.joined_at).total_seconds(), 1),
            )
        )  # fmt: skip


def _advance_crowd(db: Session, tenant: Tenant, state: QueueState, now: datetime, slow: int) -> None:
    """Demo mode: play out arrivals and plating between the last look and now."""
    if state.sim_time is None or now - state.sim_time > STALE_AFTER:
        db.execute(delete(QueueTicket).where(QueueTicket.tenant_id == tenant.id))
        state.sim_time, state.next_arrival, state.busy = now - WARM_UP, None, {}
        db.flush()
    clock_time = state.sim_time
    if now <= clock_time:
        return
    rng = world.rng_for(tenant.sim_seed or 0, "live-line", clock_time.isoformat())
    mean_service = world.SERVICE_SECONDS + world.SLOW_DISH_SECONDS * slow
    two_counter_capacity = 2 / mean_service  # people per second

    def gap(at: datetime, waiting_count: int) -> timedelta:
        # The rush comes in waves, so the line grows and drains every few minutes.
        load = 0.95 + 0.30 * math.sin(2 * math.pi * at.timestamp() / 480)
        if waiting_count < MIN_WAITING:
            load *= 1.8
        return timedelta(seconds=float(rng.exponential(1 / (two_counter_capacity * load))))

    waiting = _waiting(db, tenant.id)
    tickets = {t.id: t for t in db.scalars(select(QueueTicket).where(QueueTicket.tenant_id == tenant.id, QueueTicket.status == "called"))}
    busy = {int(counter): (int(tid), datetime.fromisoformat(free_at)) for counter, (tid, free_at) in state.busy.items()}
    counters = range(1, tenant.counters_open + 1)
    next_arrival = state.next_arrival or clock_time + gap(clock_time, len(waiting))

    def start_service(counter: int, at: datetime) -> None:
        ticket = waiting.pop(0)
        db.flush()  # the ticket needs its id before the counter can hold it
        _call(db, tenant, state, ticket, counter, at, slow)
        seconds = DEMO_PLATE_SECONDS if ticket.user_id is not None else world.service_seconds(rng, slow)
        busy[counter] = (ticket.id, at + timedelta(seconds=seconds))
        tickets[ticket.id] = ticket

    while True:
        finishing = min(busy.items(), key=lambda item: item[1][1], default=None)
        next_finish = finishing[1][1] if finishing else None
        event_time = min(t for t in (next_arrival, next_finish) if t is not None)
        if event_time > now:
            break
        if next_finish is not None and next_finish <= next_arrival:
            counter, (ticket_id, at) = finishing
            ticket = tickets.pop(ticket_id, None)
            if ticket is not None:
                ticket.status, ticket.served_at = "served", at
            del busy[counter]
            if waiting and counter in counters:
                start_service(counter, at)
        else:
            if len(waiting) < MAX_WAITING:
                waiting.append(_issue(db, tenant, state, next_arrival, None, len(waiting)))
            free = [c for c in counters if c not in busy]
            if free and waiting:
                start_service(free[0], next_arrival)
            next_arrival = next_arrival + gap(next_arrival, len(waiting))
    # A counter that opened while people were waiting starts plating straight away.
    for counter in counters:
        if counter not in busy and waiting:
            start_service(counter, now)

    state.sim_time, state.next_arrival = now, next_arrival
    state.busy = {str(counter): [tid, free_at.isoformat()] for counter, (tid, free_at) in busy.items()}
    db.execute(
        delete(QueueTicket).where(
            QueueTicket.tenant_id == tenant.id,
            QueueTicket.user_id.is_(None),
            QueueTicket.status == "served",
            QueueTicket.served_at < now - timedelta(seconds=90),
        )
    )
    db.flush()


def _estimate(db: Session, tenant: Tenant, state: QueueState, ahead: int, slow: int, now: datetime) -> tuple[int, int]:
    """(expected seconds, seconds within which 4 in 5 are served) for someone with `ahead` people in front."""
    if ahead <= 0:
        return 0, 0
    model = registry.load(registry.champion(db, tenant.id, "wait"))
    opened = window_utc(state.day, state.meal, tenant.timezone)[0]
    minute = min(max((now - opened).total_seconds() / 60, 0.0), 120.0)
    if model is not None:
        expected, upper = model.predict(ahead, tenant.counters_open, slow, minute, state.meal)
    else:
        expected = naive_wait(ahead, tenant.counters_open)
        upper = expected * 1.4
    return int(round(expected)), int(round(upper))


def snapshot(db: Session, tenant: Tenant, user: User | None = None, now: datetime | None = None) -> dict:
    """Everything a phone, the counter tablet or the wall display needs to draw the line."""
    now = now or clock.utcnow()
    with _lock:
        state, phase = _state(db, tenant, now)
        dishes = _menu(db, tenant.id, state.day, state.meal)
        slow = sum(1 for d in dishes if d.slow)
        simulated = tenant.is_demo and tenant.sim_seed is not None
        if simulated:
            _advance_crowd(db, tenant, state, now, slow)
        db.commit()

        waiting = _waiting(db, tenant.id)
        called = list(
            db.scalars(
                select(QueueTicket)
                .where(QueueTicket.tenant_id == tenant.id, QueueTicket.status == "called")
                .order_by(QueueTicket.counter)
            )
        )
        opens, closes = window_utc(state.day, state.meal, tenant.timezone)
        join_wait, join_upper = _estimate(db, tenant, state, len(waiting) + (1 if called else 0), slow, now)
        result = {
            "service": {
                "day": state.day.isoformat(),
                "meal": state.meal,
                "phase": phase,
                "opens_at": clock.iso_utc(opens),
                "closes_at": clock.iso_utc(closes),
                "preview": simulated and phase != "open",
                "menu": [{"id": d.id, "name": d.name, "veg": d.veg, "slow": d.slow} for d in dishes],
            },
            "line": {
                "waiting": len(waiting),
                "counters": tenant.counters_open,
                "now_serving": [{"counter": t.counter, "token": t.token} for t in called],
                "next_tokens": [t.token for t in waiting[:6]],
                "join_wait_s": join_wait,
                "join_wait_upper_s": join_upper,
                "simulated": simulated,
            },
            "ticket": None,
        }
        if user is not None:
            ticket = db.scalars(
                select(QueueTicket)
                .where(QueueTicket.tenant_id == tenant.id, QueueTicket.user_id == user.id)
                .order_by(QueueTicket.id.desc())
            ).first()
            if ticket is not None and ticket.status != "left":
                ahead = sum(1 for t in waiting if t.token < ticket.token) if ticket.status == "waiting" else 0
                eta, eta_upper = _estimate(db, tenant, state, ahead + 1, slow, now) if ticket.status == "waiting" else (0, 0)
                result["ticket"] = {
                    "token": ticket.token,
                    "status": ticket.status,
                    "counter": ticket.counter,
                    "ahead": ahead,
                    "eta_s": eta,
                    "eta_upper_s": eta_upper,
                    "joined_at": clock.iso_utc(ticket.joined_at),
                    "quoted_wait_s": ticket.est_wait_s,
                    "waited_s": int(((ticket.called_at or now) - ticket.joined_at).total_seconds()),
                }
        return result


def join(db: Session, tenant: Tenant, user: User, now: datetime | None = None) -> dict:
    now = now or clock.utcnow()
    snapshot(db, tenant, user, now)  # bring the line up to this moment first
    with _lock:
        state, phase = _state(db, tenant, now)
        simulated = tenant.is_demo and tenant.sim_seed is not None
        if phase != "open" and not simulated:
            raise ValueError("The counter is not open yet")
        active = db.scalar(
            select(QueueTicket).where(
                QueueTicket.tenant_id == tenant.id,
                QueueTicket.user_id == user.id,
                QueueTicket.status.in_(["waiting", "called"]),
            )
        )
        if active is None:
            db.execute(delete(QueueTicket).where(QueueTicket.tenant_id == tenant.id, QueueTicket.user_id == user.id))
            ahead = int(
                db.scalar(
                    select(func.count())
                    .select_from(QueueTicket)
                    .where(QueueTicket.tenant_id == tenant.id, QueueTicket.status == "waiting")
                )
                or 0
            )
            slow = sum(1 for d in _menu(db, tenant.id, state.day, state.meal) if d.slow)
            ticket = _issue(db, tenant, state, now, user.id, ahead)
            ticket.est_wait_s = _estimate(db, tenant, state, ahead + 1, slow, now)[0]
        db.commit()
    return snapshot(db, tenant, user, now)


def leave(db: Session, tenant: Tenant, user: User, now: datetime | None = None) -> dict:
    with _lock:
        for ticket in db.scalars(
            select(QueueTicket).where(
                QueueTicket.tenant_id == tenant.id, QueueTicket.user_id == user.id, QueueTicket.status == "waiting"
            )
        ):
            ticket.status = "left"
        db.commit()
    return snapshot(db, tenant, user, now)


def set_counters(db: Session, tenant: Tenant, count: int) -> dict:
    with _lock:
        tenant.counters_open = min(max(count, 1), 4)
        db.commit()
    return snapshot(db, tenant)


def call_next(db: Session, tenant: Tenant, counter: int, now: datetime | None = None) -> dict:
    """Counter staff: this counter is done with its diner, send the next token."""
    now = now or clock.utcnow()
    with _lock:
        state, _ = _state(db, tenant, now)
        slow = sum(1 for d in _menu(db, tenant.id, state.day, state.meal) if d.slow)
        busy = dict(state.busy)
        for ticket in db.scalars(
            select(QueueTicket).where(
                QueueTicket.tenant_id == tenant.id, QueueTicket.status == "called", QueueTicket.counter == counter
            )
        ):
            ticket.status, ticket.served_at = "served", now
        busy.pop(str(counter), None)
        waiting = _waiting(db, tenant.id)
        if waiting and 1 <= counter <= tenant.counters_open:
            ticket = waiting[0]
            _call(db, tenant, state, ticket, counter, now, slow)
            seconds = world.SERVICE_SECONDS + world.SLOW_DISH_SECONDS * slow
            busy[str(counter)] = [ticket.id, (now + timedelta(seconds=seconds)).isoformat()]
        state.busy = busy
        db.commit()
    return snapshot(db, tenant, now=now)
