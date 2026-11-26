"""Numbers behind the manager's pages: waste, cost, forecast accuracy, dish statistics."""

from __future__ import annotations

import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..meals import MEAL_INDEX, MEALS
from ..ml.features import HEADLINE, load_dishes, load_meals
from ..models import CalendarDay, MealService, Tenant

KG_PER_MEAL = 0.45  # a full plate, used to express waste as "meals"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_cache: dict[int, tuple[float, tuple, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]] = {}
_CACHE_SECONDS = 20


def _num(value, digits: int = 1):
    """JSON-safe rounding: NaN and infinities become null."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    return round(float(value), digits)


def tables(db: Session, tenant: Tenant) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(sittings, dish rows, raw meals). Cached briefly; invalidated when anything new is logged."""
    stamp = tuple(
        db.execute(
            select(func.count(MealService.served), func.max(MealService.logged_at), func.max(MealService.forecast_at)).where(
                MealService.tenant_id == tenant.id
            )
        ).one()
    )
    cached = _cache.get(tenant.id)
    if cached and cached[1] == stamp and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[2]

    meals, dishes = load_meals(db, tenant.id), load_dishes(db, tenant.id)
    rows = dishes[dishes["prepared_kg"].notna()].copy()
    rows["consumed_kg"] = rows["prepared_kg"] - rows["leftover_kg"]
    rows["left_cost"] = rows["leftover_kg"] * rows["cost_per_kg"]
    rows["left_co2"] = rows["leftover_kg"] * rows["co2_per_kg"]
    rows["cooked_cost"] = rows["prepared_kg"] * rows["cost_per_kg"]
    rows["cooked_co2"] = rows["prepared_kg"] * rows["co2_per_kg"]
    per_sitting = (
        rows.groupby(["day", "meal"], sort=False)
        .agg(
            prepared_kg=("prepared_kg", "sum"),
            leftover_kg=("leftover_kg", "sum"),
            runouts=("ran_out", "sum"),
            n_dishes=("dish_id", "size"),
            left_cost=("left_cost", "sum"),
            left_co2=("left_co2", "sum"),
            cooked_cost=("cooked_cost", "sum"),
            cooked_co2=("cooked_co2", "sum"),
        )
        .reset_index()
    )
    sittings = meals[meals["served"].notna()].merge(per_sitting, on=["day", "meal"], how="inner")
    other = sittings["plate_waste_kg"].fillna(0) + sittings["prep_waste_kg"].fillna(0)
    cooked = sittings["prepared_kg"].replace(0, np.nan)
    sittings["waste_kg"] = sittings["leftover_kg"] + other
    sittings["cost"] = sittings["left_cost"] + other * (sittings["cooked_cost"] / cooked).fillna(0)
    sittings["co2"] = sittings["left_co2"] + other * (sittings["cooked_co2"] / cooked).fillna(0)
    sittings["abs_error"] = (sittings["forecast_p50"] - sittings["served"]).abs()
    sittings["in_band"] = (sittings["served"] >= sittings["forecast_p10"]) & (sittings["served"] <= sittings["forecast_p90"])
    sittings["off"] = sittings["kind"].isin(["holiday", "break"])
    rows = rows.merge(sittings[["day", "meal", "served", "mode", "off"]], on=["day", "meal"], how="inner")
    result = (sittings, rows, meals)
    _cache[tenant.id] = (time.monotonic(), stamp, result)
    return result


def _period(sittings: pd.DataFrame) -> dict:
    """Headline measures for a set of sittings."""
    if sittings.empty:
        return {"sittings": 0}
    served = sittings["served"].sum()
    prepared = sittings["prepared_kg"].sum()
    days = max(sittings["day"].nunique(), 1)
    with_forecast = sittings[sittings["forecast_p50"].notna() & (sittings["served"] > 0)]
    return {
        "sittings": int(len(sittings)),
        "days": int(days),
        "served": int(served),
        "waste_kg": _num(sittings["waste_kg"].sum()),
        "leftover_kg": _num(sittings["leftover_kg"].sum()),
        "plate_kg": _num(sittings["plate_waste_kg"].sum()),
        "prep_kg": _num(sittings["prep_waste_kg"].sum()),
        "prepared_kg": _num(prepared),
        "waste_per_head_g": _num(sittings["waste_kg"].sum() * 1000 / served if served else None),
        "leftover_pct": _num(sittings["leftover_kg"].sum() / prepared * 100 if prepared else None),
        "runout_pct": _num(sittings["runouts"].sum() / sittings["n_dishes"].sum() * 100),
        "cost": _num(sittings["cost"].sum(), 0),
        "co2_kg": _num(sittings["co2"].sum(), 0),
        "meals_equivalent": _num((sittings["leftover_kg"].sum() + sittings["plate_waste_kg"].sum()) / KG_PER_MEAL, 0),
        "waste_kg_per_day": _num(sittings["waste_kg"].sum() / days),
        "forecast_mape": _num((with_forecast["abs_error"] / with_forecast["served"]).mean() * 100 if len(with_forecast) else None),
        "forecast_mae": _num(with_forecast["abs_error"].mean() if len(with_forecast) else None),
    }


def _range(sittings: pd.DataFrame, first: date, last: date) -> pd.DataFrame:
    return sittings[(sittings["day"] >= pd.Timestamp(first)) & (sittings["day"] <= pd.Timestamp(last))]


def adoption(tenant: Tenant, sittings: pd.DataFrame, rows: pd.DataFrame) -> dict | None:
    """Before and after the kitchen started cooking from the sheet, and what that saved."""
    if tenant.katori_since is None or sittings.empty:
        return None
    since = pd.Timestamp(tenant.katori_since)
    before, after = sittings[sittings["day"] < since], sittings[sittings["day"] >= since]
    if before.empty or after.empty:
        return None
    # Same days, same appetite: what the old fixed rule would have left in the pots.
    live = rows[rows["day"] >= since].copy()
    got_it = (live["served"] - live["short_heads"]).clip(lower=1)
    wanted = np.where(live["ran_out"], live["consumed_kg"] * live["served"] / got_it, live["consumed_kg"])
    rule_left = (live["habit_kg"] - wanted).clip(lower=0)
    saved_kg = float((rule_left - live["leftover_kg"]).sum())
    saved_cost = float(((rule_left - live["leftover_kg"]) * live["cost_per_kg"]).sum())
    saved_co2 = float(((rule_left - live["leftover_kg"]) * live["co2_per_kg"]).sum())
    weeks = max(after["day"].nunique() / 7, 1e-9)
    return {
        "since": tenant.katori_since.isoformat(),
        "before": _period(before),
        "after": _period(after),
        "saved_kg": _num(saved_kg, 0),
        "saved_kg_per_week": _num(saved_kg / weeks, 0),
        "saved_cost_per_month": _num(saved_cost / weeks * 30 / 7, 0),
        "saved_co2_kg": _num(saved_co2, 0),
        "saved_meals": _num(saved_kg / KG_PER_MEAL, 0),
        "old_rule_runout_pct": _num(float((wanted > live["habit_kg"] * 1.01).mean() * 100)),
    }


def weekly_trend(db: Session, tenant: Tenant, sittings: pd.DataFrame) -> list[dict]:
    if sittings.empty:
        return []
    frame = sittings.copy()
    frame["week"] = frame["day"] - pd.to_timedelta(frame["day"].dt.day_of_week, unit="D")
    labels: dict[pd.Timestamp, list[str]] = {}
    for marked in db.scalars(select(CalendarDay).where(CalendarDay.tenant_id == tenant.id)):
        week = pd.Timestamp(marked.day - timedelta(days=marked.day.weekday()))
        if marked.label not in labels.setdefault(week, []):
            labels[week].append(marked.label)
    since = pd.Timestamp(tenant.katori_since) if tenant.katori_since else None
    trend = []
    for week, group in frame.groupby("week", sort=True):
        if group["day"].nunique() < 7:
            continue  # a part-week would look like a dip
        summary = _period(group)
        trend.append(
            {
                "week": week.date().isoformat(),
                "leftover_kg": summary["leftover_kg"],
                "plate_kg": summary["plate_kg"],
                "prep_kg": summary["prep_kg"],
                "waste_per_head_g": summary["waste_per_head_g"],
                "leftover_pct": summary["leftover_pct"],
                "runout_pct": summary["runout_pct"],
                "served": summary["served"],
                "forecast_mae": summary["forecast_mae"],
                "phase": "sheet" if since is not None and week + pd.Timedelta(days=6) >= since else "habit",
                "labels": labels.get(week, []),
            }
        )
    return trend


def dish_stats(sittings: pd.DataFrame, rows: pd.DataFrame, strength: int, days: int | None = None) -> pd.DataFrame:
    """Per dish: how often served, how much comes back, how it is rated, and what it does to turnout."""
    if rows.empty:
        return pd.DataFrame()
    if days:
        cut = rows["day"].max() - pd.Timedelta(days=days - 1)
        rows, sittings = rows[rows["day"] >= cut], sittings[sittings["day"] >= cut]
    usual = sittings[~sittings["off"]].copy()
    usual["ratio"] = usual["served"] / strength
    # Compare like with like: a Tuesday dinner against other Monday-to-Thursday dinners, while
    # Friday, Saturday and Sunday each have their own crowd and are only compared with themselves.
    weekday = usual["day"].dt.day_of_week
    usual["crowd"] = np.where(weekday <= 3, "weekday", weekday.astype(str))
    usual["lift"] = usual["ratio"] - usual.groupby(["meal", "crowd"])["ratio"].transform("mean")
    joined = rows.merge(usual[["day", "meal", "lift"]], on=["day", "meal"], how="left")
    stats = joined.groupby(["dish_id", "name", "category", "veg"], sort=False).agg(
        times=("day", "size"),
        prepared_kg=("prepared_kg", "sum"),
        leftover_kg=("leftover_kg", "sum"),
        runouts=("ran_out", "sum"),
        rating_sum=("rating_sum", "sum"),
        rating_n=("rating_n", "sum"),
        left_cost=("left_cost", "sum"),
        lift_sum=("lift", "sum"),
        lift_n=("lift", "count"),
    )
    stats = stats.reset_index()
    stats["leftover_pct"] = stats["leftover_kg"] / stats["prepared_kg"].replace(0, np.nan) * 100
    stats["rating"] = stats["rating_sum"] / stats["rating_n"].replace(0, np.nan)
    # Shrunk towards zero so a dish served twice cannot claim a big effect.
    stats["turnout_lift"] = stats["lift_sum"] / (stats["lift_n"] + 2) * strength
    return stats


def _dish_record(row) -> dict:
    return {
        "dish_id": int(row.dish_id),
        "name": row.name,
        "category": row.category,
        "veg": bool(row.veg),
        "times": int(row.times),
        "prepared_kg": _num(row.prepared_kg),
        "leftover_kg": _num(row.leftover_kg),
        "leftover_pct": _num(row.leftover_pct),
        "runouts": int(row.runouts),
        "rating": _num(row.rating, 2),
        "ratings": int(row.rating_n),
        "cost": _num(row.left_cost, 0),
        "turnout_lift": _num(row.turnout_lift),
    }


def insights(tenant: Tenant, sittings: pd.DataFrame, rows: pd.DataFrame, meals: pd.DataFrame) -> list[dict]:
    """Plain-language findings from the last four weeks."""
    found: list[dict] = []
    if sittings.empty:
        return found
    cut = sittings["day"].max() - pd.Timedelta(days=27)
    recent, recent_rows = sittings[sittings["day"] >= cut], rows[rows["day"] >= cut]
    stats = dish_stats(recent, recent_rows, tenant.strength)
    if not stats.empty:
        regulars = stats[(stats["times"] >= 3) & stats["category"].isin(HEADLINE)]
        if not regulars.empty:
            worst = regulars.sort_values("leftover_pct", ascending=False).iloc[0]
            if worst.leftover_pct >= 12:
                found.append(
                    {
                        "tone": "waste",
                        "title": f"{worst['name']} comes back the most",
                        "body": f"{worst.leftover_pct:.0f}% of what is cooked is never served "
                        f"({worst.leftover_kg:.0f} kg over {int(worst.times)} sittings, about ₹{worst.left_cost:,.0f}).",
                        "metric": f"{worst.leftover_pct:.0f}%",
                    }
                )
            dry = regulars.sort_values("runouts", ascending=False).iloc[0]
            if dry.runouts >= 2:
                found.append(
                    {
                        "tone": "info",
                        "title": f"{dry['name']} keeps running out",
                        "body": f"The pot ran dry at {int(dry.runouts)} of {int(dry.times)} sittings. "
                        "Residents want more of it than the sheet allows for; log who missed out so the model learns.",
                        "metric": f"{int(dry.runouts)}x",
                    }
                )
            rated = regulars[regulars["rating_n"] >= 15]
            if len(rated) >= 2:
                low, high = rated.sort_values("rating").iloc[0], rated.sort_values("rating").iloc[-1]
                if low.rating < 3:
                    crowd = (
                        f", and about {abs(low.turnout_lift):.0f} fewer residents turn up when it is on"
                        if low.turnout_lift <= -3
                        else ""
                    )
                    found.append(
                        {
                            "tone": "waste",
                            "title": f"{low['name']} is the lowest rated dish",
                            "body": f"{low.rating:.1f} stars from {int(low.rating_n)} ratings{crowd}. "
                            f"{high['name']} leads at {high.rating:.1f}.",
                            "metric": f"{low.rating:.1f}",
                        }
                    )
    slot = recent.assign(weekday=recent["day"].dt.day_of_week).groupby(["weekday", "meal"]).agg(
        waste=("waste_kg", "sum"), served=("served", "sum")
    )
    slot["per_head"] = slot["waste"] * 1000 / slot["served"].replace(0, np.nan)
    if slot["per_head"].notna().any():
        (weekday, meal), worst_slot = slot["per_head"].idxmax(), slot["per_head"].max()
        found.append(
            {
                "tone": "waste",
                "title": f"{WEEKDAYS[weekday]} {meal} wastes the most per person",
                "body": f"{worst_slot:.0f} g per resident served, against {recent['waste_kg'].sum() * 1000 / recent['served'].sum():.0f} g across all sittings.",
                "metric": f"{worst_slot:.0f} g",
            }
        )
    week = meals[(meals["day"] > sittings["day"].max() - pd.Timedelta(days=7)) & meals["served"].notna()]
    if len(week):
        notices = int(week["skips"].sum())
        found.append(
            {
                "tone": "good",
                "title": f"{notices:,} skip notices in the last week",
                "body": f"Each one is a plate the kitchen did not have to guess about: roughly {notices * KG_PER_MEAL:,.0f} kg "
                "of food that was never cooked for someone who was not coming.",
                "metric": f"{notices:,}",
            }
        )
    return found


def overview(db: Session, tenant: Tenant, days: int = 28) -> dict:
    sittings, rows, meals = tables(db, tenant)
    if sittings.empty:
        return {"empty": True}
    last = sittings["day"].max().date()
    current = _range(sittings, last - timedelta(days=days - 1), last)
    previous = _range(sittings, last - timedelta(days=2 * days - 1), last - timedelta(days=days))
    daily = []
    for day, group in current.groupby("day", sort=True):
        daily.append(
            {
                "day": day.date().isoformat(),
                "leftover_kg": _num(group["leftover_kg"].sum()),
                "plate_kg": _num(group["plate_waste_kg"].sum()),
                "prep_kg": _num(group["prep_waste_kg"].sum()),
                "served": int(group["served"].sum()),
                "kind": group["kind"].iloc[0],
            }
        )
    return {
        "empty": False,
        "range": {"from": (last - timedelta(days=days - 1)).isoformat(), "to": last.isoformat(), "days": days},
        "current": _period(current),
        "previous": _period(previous),
        "adoption": adoption(tenant, sittings, rows),
        "trend": weekly_trend(db, tenant, sittings),
        "daily": daily,
        "insights": insights(tenant, sittings, rows, meals),
    }


def waste_breakdown(db: Session, tenant: Tenant, days: int = 28) -> dict:
    sittings, rows, _ = tables(db, tenant)
    if sittings.empty:
        return {"empty": True}
    last = sittings["day"].max().date()
    first = last - timedelta(days=days - 1)
    current, current_rows = _range(sittings, first, last), _range(rows, first, last)
    stats = dish_stats(current, current_rows, tenant.strength)
    by_dish = [_dish_record(row) for row in stats.sort_values("leftover_kg", ascending=False).itertuples(index=False)]

    slots = current.assign(weekday=current["day"].dt.day_of_week).groupby(["weekday", "meal"]).agg(
        waste=("waste_kg", "sum"), served=("served", "sum"), leftover=("leftover_kg", "sum"), prepared=("prepared_kg", "sum")
    )
    heatmap = [
        {
            "weekday": int(weekday),
            "meal": meal,
            "waste_per_head_g": _num(row.waste * 1000 / row.served if row.served else None),
            "leftover_pct": _num(row.leftover / row.prepared * 100 if row.prepared else None),
        }
        for (weekday, meal), row in slots.iterrows()
    ]
    by_meal = [
        {"meal": meal, **{k: v for k, v in _period(current[current["meal"] == meal]).items() if k in {
            "waste_kg", "leftover_kg", "plate_kg", "prep_kg", "waste_per_head_g", "leftover_pct", "runout_pct", "served"}}}
        for meal in MEALS
        if (current["meal"] == meal).any()
    ]  # fmt: skip
    categories = current_rows.groupby("category").agg(leftover=("leftover_kg", "sum"), prepared=("prepared_kg", "sum"))
    by_category = [
        {"category": name, "leftover_kg": _num(row.leftover), "leftover_pct": _num(row.leftover / row.prepared * 100 if row.prepared else None)}
        for name, row in categories.sort_values("leftover", ascending=False).iterrows()
    ]
    return {
        "empty": False,
        "range": {"from": first.isoformat(), "to": last.isoformat(), "days": days},
        "totals": _period(current),
        "by_dish": by_dish,
        "heatmap": heatmap,
        "by_meal": by_meal,
        "by_category": by_category,
    }


def forecast_view(db: Session, tenant: Tenant) -> dict:
    sittings, _, meals = tables(db, tenant)
    labels = {c.day: c.label for c in db.scalars(select(CalendarDay).where(CalendarDay.tenant_id == tenant.id))}
    upcoming = meals[meals["served"].isna()].copy()
    upcoming["order"] = upcoming["meal"].map(MEAL_INDEX)
    ahead = [
        {
            "day": row.day.date().isoformat(),
            "meal": row.meal,
            "expected": _num(row.forecast_p50, 0),
            "low": _num(row.forecast_p10, 0),
            "high": _num(row.forecast_p90, 0),
            "final": str(row.forecast_model).startswith("cook"),
            "skips": int(row.skips),
            "kind": row.kind,
            "label": labels.get(row.day.date(), ""),
        }
        for row in upcoming.sort_values(["day", "order"]).itertuples(index=False)
    ]
    scored = sittings[sittings["forecast_p50"].notna()].copy()
    scored["order"] = scored["meal"].map(MEAL_INDEX)
    recent = scored[scored["day"] > scored["day"].max() - pd.Timedelta(days=21)] if len(scored) else scored
    history = [
        {
            "day": row.day.date().isoformat(),
            "meal": row.meal,
            "forecast": _num(row.forecast_p50, 0),
            "low": _num(row.forecast_p10, 0),
            "high": _num(row.forecast_p90, 0),
            "actual": int(row.served),
            "kind": row.kind,
        }
        for row in recent.sort_values(["day", "order"]).itertuples(index=False)
    ]
    month = scored[scored["day"] > scored["day"].max() - pd.Timedelta(days=28)] if len(scored) else scored
    eaten = month[month["served"] > 0]
    by_meal = [
        {"meal": meal, "mae": _num(month.loc[month["meal"] == meal, "abs_error"].mean())}
        for meal in MEALS
        if (month["meal"] == meal).any()
    ]
    return {
        "strength": tenant.strength,
        "upcoming": ahead,
        "recent": history,
        "live": {
            "sittings": int(len(month)),
            "mae": _num(month["abs_error"].mean() if len(month) else None),
            "mape": _num((eaten["abs_error"] / eaten["served"]).mean() * 100 if len(eaten) else None),
            "in_band_pct": _num(month["in_band"].mean() * 100 if len(month) else None),
            "by_meal": by_meal,
        },
    }


def public_summary(db: Session, tenant: Tenant) -> dict:
    """The handful of numbers shown before sign-in."""
    sittings, rows, _ = tables(db, tenant)
    change = adoption(tenant, sittings, rows) if not sittings.empty else None
    scored = sittings[sittings["forecast_p50"].notna() & (sittings["served"] > 0) & ~sittings["off"]] if not sittings.empty else sittings
    recent = scored[scored["day"] > scored["day"].max() - pd.Timedelta(days=28)] if len(scored) else scored
    return {
        "hostel": tenant.name,
        "city": tenant.city,
        "residents": tenant.strength,
        "sittings_logged": int(len(sittings)),
        "weeks": int(sittings["day"].nunique() // 7) if not sittings.empty else 0,
        "forecast_mape": _num((recent["abs_error"] / recent["served"]).mean() * 100 if len(recent) else None),
        "leftover_before_pct": change["before"]["leftover_pct"] if change else None,
        "leftover_after_pct": change["after"]["leftover_pct"] if change else None,
        "saved_kg_per_week": change["saved_kg_per_week"] if change else None,
        "simulated": tenant.sim_seed is not None,
        "data_through": sittings["day"].max().date().isoformat() if not sittings.empty else None,
        "today": clock.local_today(tenant.timezone).isoformat(),
    }


def forget_cache() -> None:
    _cache.clear()
