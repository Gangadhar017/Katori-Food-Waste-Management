"""Tables. Every row that belongs to a kitchen carries its tenant_id."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import utcnow
from .db import Base


class Tenant(Base):
    """One kitchen that subscribes to Katori: a hostel mess today, a restaurant later."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="hostel")
    city: Mapped[str] = mapped_column(String(80), default="")
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Kolkata")
    strength: Mapped[int]
    # First day the kitchen cooked from Katori's sheet instead of habit.
    katori_since: Mapped[date | None] = mapped_column(Date, default=None)
    # How sure the kitchen wants to be that a pot does not run dry (0.95 = short on 1 dish in 20).
    service_level: Mapped[float] = mapped_column(default=0.95)
    counters_open: Mapped[int] = mapped_column(default=2)
    is_demo: Mapped[bool] = mapped_column(default=False)
    sim_seed: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # student | kitchen | manager
    password_hash: Mapped[str] = mapped_column(String(200))
    room: Mapped[str] = mapped_column(String(20), default="")
    diet: Mapped[str] = mapped_column(String(10), default="veg")
    points: Mapped[int] = mapped_column(default=0)
    streak: Mapped[int] = mapped_column(default=0)
    last_active: Mapped[date | None] = mapped_column(Date, default=None)  # last day they helped the kitchen
    is_demo: Mapped[bool] = mapped_column(default=False)
    is_sim: Mapped[bool] = mapped_column(default=False)

    tenant: Mapped[Tenant] = relationship()


class Dish(Base):
    __tablename__ = "dishes"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(20))
    veg: Mapped[bool] = mapped_column(default=True)
    portion_g: Mapped[float]  # standard cooked portion per person
    piece_g: Mapped[float | None] = mapped_column(default=None)  # set for countable items (roti, samosa)
    cost_per_kg: Mapped[float]  # rupees per cooked kg
    co2_per_kg: Mapped[float]  # kg CO2e per cooked kg, a rough category estimate
    slow: Mapped[bool] = mapped_column(default=False)  # made to order at the counter, slows the line
    ingredients: Mapped[list] = mapped_column(JSON, default=list)  # [{name, g_per_kg}]
    active: Mapped[bool] = mapped_column(default=True)


class MenuTemplate(Base):
    """The weekly food chart: which dishes are planned for each weekday and meal."""

    __tablename__ = "menu_template"
    __table_args__ = (UniqueConstraint("tenant_id", "weekday", "meal", "dish_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    weekday: Mapped[int]  # 0 = Monday
    meal: Mapped[str] = mapped_column(String(12))
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    position: Mapped[int] = mapped_column(default=0)


class MenuEntry(Base):
    """What was, or will be, on the counter on a given date."""

    __tablename__ = "menu_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "day", "meal", "dish_id"),
        Index("ix_menu_day", "tenant_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    position: Mapped[int] = mapped_column(default=0)

    dish: Mapped[Dish] = relationship()


class CalendarDay(Base):
    __tablename__ = "calendar_days"
    __table_args__ = (UniqueConstraint("tenant_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(12))  # holiday | break | exam | fest
    label: Mapped[str] = mapped_column(String(80))


class MealService(Base):
    """One sitting of one meal: its context, its forecast and what really happened."""

    __tablename__ = "meal_services"
    __table_args__ = (
        UniqueConstraint("tenant_id", "day", "meal"),
        Index("ix_service_day", "tenant_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))

    # Context known before the meal.
    calendar_kind: Mapped[str] = mapped_column(String(12), default="")
    rain_mm: Mapped[float] = mapped_column(default=0.0)
    temp_c: Mapped[float] = mapped_column(default=25.0)
    skips: Mapped[int] = mapped_column(default=0)  # residents who said in time they will not eat

    # Forecast written before the meal; never overwritten afterwards, so it scores honestly.
    forecast_p10: Mapped[float | None] = mapped_column(default=None)
    forecast_p50: Mapped[float | None] = mapped_column(default=None)
    forecast_p90: Mapped[float | None] = mapped_column(default=None)
    forecast_model: Mapped[str] = mapped_column(String(40), default="")
    forecast_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # Actuals, filled by the kitchen after service.
    mode: Mapped[str] = mapped_column(String(10), default="")  # habit | katori
    served: Mapped[int | None] = mapped_column(default=None)
    prep_waste_kg: Mapped[float | None] = mapped_column(default=None)
    plate_waste_kg: Mapped[float | None] = mapped_column(default=None)
    logged_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    logged_by: Mapped[str] = mapped_column(String(20), default="")  # kitchen | simulator


class DishService(Base):
    """One dish at one sitting: how much was advised, cooked and left in the pot."""

    __tablename__ = "dish_services"
    __table_args__ = (
        UniqueConstraint("tenant_id", "day", "meal", "dish_id"),
        Index("ix_dish_service_day", "tenant_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))

    habit_kg: Mapped[float | None] = mapped_column(default=None)  # what the old fixed rule would cook
    recommended_kg: Mapped[float | None] = mapped_column(default=None)
    prepared_kg: Mapped[float | None] = mapped_column(default=None)
    leftover_kg: Mapped[float | None] = mapped_column(default=None)  # cooked, never served
    ran_out: Mapped[bool] = mapped_column(default=False)
    short_heads: Mapped[int] = mapped_column(default=0)  # diners who went without because the pot ran dry
    rating_sum: Mapped[float] = mapped_column(default=0.0)
    rating_n: Mapped[int] = mapped_column(default=0)

    dish: Mapped[Dish] = relationship()


class Rsvp(Base):
    """A resident's word on one meal. No row means the default: they will eat."""

    __tablename__ = "rsvps"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "day", "meal"),
        Index("ix_rsvp_meal", "tenant_id", "day", "meal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(8))  # eat | skip
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "day", "meal", "dish_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    stars: Mapped[int]
    portion: Mapped[str] = mapped_column(String(8), default="right")  # less | right | more
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QueueTicket(Base):
    __tablename__ = "queue_tickets"
    __table_args__ = (Index("ix_ticket_service", "tenant_id", "day", "meal", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    token: Mapped[int]
    status: Mapped[str] = mapped_column(String(10), default="waiting")  # waiting | called | served | left
    counter: Mapped[int | None] = mapped_column(default=None)
    joined_at: Mapped[datetime] = mapped_column(DateTime)
    called_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    served_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ahead_at_join: Mapped[int] = mapped_column(default=0)
    est_wait_s: Mapped[int] = mapped_column(default=0)


class QueueState(Base):
    """Where the line stands. In demo mode it also holds the simulated crowd's clock."""

    __tablename__ = "queue_state"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))
    next_token: Mapped[int] = mapped_column(default=1)
    sim_time: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    next_arrival: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    busy: Mapped[dict] = mapped_column(JSON, default=dict)  # counter number -> ISO time it frees up


class WaitSample(Base):
    """One finished wait, kept as training data for the wait-time model."""

    __tablename__ = "wait_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(12))
    minute: Mapped[float]  # minutes since the counter opened
    ahead: Mapped[int]
    counters: Mapped[int]
    slow_dishes: Mapped[int]
    wait_s: Mapped[float]


class GameScore(Base):
    __tablename__ = "game_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    game: Mapped[str] = mapped_column(String(20))
    score: Mapped[int]
    points: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PointEvent(Base):
    """Ledger behind a resident's points, so the leaderboard can be recomputed and audited."""

    __tablename__ = "point_events"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "reason", "ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(String(20))  # skip | rating | game | streak
    ref: Mapped[str] = mapped_column(String(60))  # what it was for, unique per reason
    points: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ModelRun(Base):
    """Model registry: every training run, its backtest scores and whether it serves."""

    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # headcount_cook | headcount_outlook | portion | wait
    algorithm: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12))  # champion | retired | rejected
    trained_at: Mapped[datetime] = mapped_column(DateTime)
    train_through: Mapped[date | None] = mapped_column(Date, default=None)
    n_rows: Mapped[int] = mapped_column(default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # candidates, importances, quantiles
    note: Mapped[str] = mapped_column(String(200), default="")
    path: Mapped[str] = mapped_column(String(200), default="")
