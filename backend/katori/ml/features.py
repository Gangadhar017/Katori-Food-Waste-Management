"""Turns the kitchen's log into model inputs.

Every feature of a sitting is built only from information available before that sitting:
lags look back, dish statistics use prior occurrences only. The same code builds rows
for training (sittings that happened) and for forecasting (sittings still to come).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..meals import MEAL_INDEX, MEALS
from ..models import Dish, DishService, MealService, MenuEntry

DEFAULT_RATE = {"breakfast": 0.60, "lunch": 0.80, "snacks": 0.50, "dinner": 0.85}
HEADLINE = ("breakfast", "dal", "sabzi", "special", "snack", "dessert")
CATEGORIES = ("breakfast", "staple", "dal", "sabzi", "special", "snack", "side", "dessert", "beverage")
CALENDAR_KINDS = ("holiday", "break", "exam", "fest")
UNCOUNTED_SHORTFALL = 1.06  # demand assumed for a pot that ran dry with nobody counting who missed out
MEAL_WEEKDAY_COLUMNS = [f"mw_{meal}_{weekday}" for meal in MEALS for weekday in range(7)]


def load_meals(db: Session, tenant_id: int) -> pd.DataFrame:
    rows = db.execute(
        select(
            MealService.day,
            MealService.meal,
            MealService.calendar_kind,
            MealService.rain_mm,
            MealService.temp_c,
            MealService.skips,
            MealService.served,
            MealService.forecast_p50,
            MealService.mode,
            MealService.forecast_p10,
            MealService.forecast_p90,
            MealService.forecast_model,
            MealService.prep_waste_kg,
            MealService.plate_waste_kg,
        ).where(MealService.tenant_id == tenant_id)
    ).all()
    frame = pd.DataFrame(
        rows,
        columns=[
            "day", "meal", "kind", "rain_mm", "temp_c", "skips", "served", "forecast_p50", "mode",
            "forecast_p10", "forecast_p90", "forecast_model", "prep_waste_kg", "plate_waste_kg",
        ],
    )  # fmt: skip
    frame["day"] = pd.to_datetime(frame["day"])
    # Explicit types, so a kitchen with nothing logged yet still yields well-formed (empty) columns.
    for column in (
        "rain_mm", "temp_c", "skips", "served", "forecast_p50", "forecast_p10", "forecast_p90",
        "prep_waste_kg", "plate_waste_kg",
    ):  # fmt: skip
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    for column in ("meal", "kind", "mode", "forecast_model"):
        frame[column] = frame[column].fillna("").astype(str)
    return frame


def load_dishes(db: Session, tenant_id: int) -> pd.DataFrame:
    rows = db.execute(
        select(
            MenuEntry.day,
            MenuEntry.meal,
            MenuEntry.dish_id,
            Dish.name,
            Dish.category,
            Dish.veg,
            Dish.portion_g,
            Dish.slow,
            Dish.cost_per_kg,
            Dish.co2_per_kg,
            DishService.habit_kg,
            DishService.recommended_kg,
            DishService.prepared_kg,
            DishService.leftover_kg,
            DishService.ran_out,
            DishService.short_heads,
            DishService.rating_sum,
            DishService.rating_n,
        )
        .join(Dish, Dish.id == MenuEntry.dish_id)
        .outerjoin(
            DishService,
            and_(
                DishService.tenant_id == MenuEntry.tenant_id,
                DishService.day == MenuEntry.day,
                DishService.meal == MenuEntry.meal,
                DishService.dish_id == MenuEntry.dish_id,
            ),
        )
        .where(MenuEntry.tenant_id == tenant_id)
    ).all()
    frame = pd.DataFrame(
        rows,
        columns=[
            "day", "meal", "dish_id", "name", "category", "veg", "portion_g", "slow", "cost_per_kg", "co2_per_kg",
            "habit_kg", "recommended_kg", "prepared_kg", "leftover_kg", "ran_out", "short_heads",
            "rating_sum", "rating_n",
        ],
    )  # fmt: skip
    frame["day"] = pd.to_datetime(frame["day"])
    frame["short_heads"] = pd.to_numeric(frame["short_heads"], errors="coerce").fillna(0.0).astype(float)
    for column in ("habit_kg", "recommended_kg", "prepared_kg", "leftover_kg", "portion_g", "cost_per_kg", "co2_per_kg"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    frame["dish_id"] = pd.to_numeric(frame["dish_id"], errors="coerce").fillna(0).astype(int)
    for column in ("meal", "name", "category"):
        frame[column] = frame[column].fillna("").astype(str)
    frame["ran_out"] = frame["ran_out"].fillna(False).astype(bool)
    frame["veg"] = frame["veg"].astype(bool)
    frame["slow"] = frame["slow"].astype(bool)
    frame["rating_sum"] = pd.to_numeric(frame["rating_sum"], errors="coerce").fillna(0.0).astype(float)
    frame["rating_n"] = pd.to_numeric(frame["rating_n"], errors="coerce").fillna(0.0).astype(float)
    return frame


def _lagged(frame: pd.DataFrame, days: int, name: str) -> pd.DataFrame:
    """Join each sitting to the same meal `days` earlier."""
    earlier = frame[["day", "meal", "usual"]].rename(columns={"usual": name})
    earlier["day"] = earlier["day"] + pd.Timedelta(days=days)
    return frame.merge(earlier, on=["day", "meal"], how="left")


def headcount_frame(meals: pd.DataFrame, dishes: pd.DataFrame, strength: int) -> pd.DataFrame:
    """One row per sitting with turnout features. `ratio` (turnout / roll) is NaN for future sittings."""
    m = meals.copy()
    m["meal_idx"] = m["meal"].map(MEAL_INDEX).astype(int)
    m = m.sort_values(["day", "meal_idx"]).reset_index(drop=True)
    m["ratio"] = m["served"] / strength
    m["weekday"] = m["day"].dt.day_of_week.astype(int)
    m["dom"] = m["day"].dt.day.astype(int)
    m["month_end"] = (m["dom"] >= 25).astype(int)
    for kind in CALENDAR_KINDS:
        m[f"is_{kind}"] = (m["kind"] == kind).astype(int)
    m["skip_share"] = m["skips"].astype(float) / strength

    # "Usual" turnout: holidays and breaks are left out of every lag and average, so one empty
    # week does not drag the forecast down for a month afterwards.
    m["usual"] = m["ratio"].where(~m["kind"].isin(["holiday", "break"]))
    m = _lagged(m, 7, "lag7")
    m = _lagged(m, 14, "lag14")

    by_meal = m.groupby("meal", sort=False)["usual"]
    m["meal_mean"] = by_meal.transform(lambda s: s.shift(1).expanding(min_periods=1).mean())
    m["roll7d"] = by_meal.transform(lambda s: s.shift(1).rolling(7, min_periods=3).mean())
    m["roll4w"] = m.groupby(["meal", "weekday"], sort=False)["usual"].transform(
        lambda s: s.shift(1).rolling(4, min_periods=1).mean()
    )
    m["meal_mean"] = m["meal_mean"].fillna(m["meal"].map(DEFAULT_RATE))
    m["roll4w"] = m["roll4w"].fillna(m["meal_mean"])
    m["roll7d"] = m["roll7d"].fillna(m["meal_mean"])
    m["lag7"] = m["lag7"].fillna(m["roll4w"])
    m["lag14"] = m["lag14"].fillna(m["lag7"])

    # Dish statistics: how each dish has moved turnout and how it has been rated, before this sitting.
    d = dishes.merge(m[["day", "meal", "meal_idx", "usual", "meal_mean"]], on=["day", "meal"], how="inner")
    d = d.sort_values(["day", "meal_idx", "dish_id"]).reset_index(drop=True)
    residual = d["usual"] - d["meal_mean"]
    d["_r"] = residual.fillna(0.0)
    d["_k"] = residual.notna().astype(float)
    grouped = d.groupby("dish_id", sort=False)
    prior_sum = grouped["_r"].cumsum() - d["_r"]
    prior_n = grouped["_k"].cumsum() - d["_k"]
    d["pull"] = prior_sum / (prior_n + 3.0)
    prior_stars = grouped["rating_sum"].cumsum() - d["rating_sum"]
    prior_votes = grouped["rating_n"].cumsum() - d["rating_n"]
    d["rating"] = (prior_stars + 3.5 * 5) / (prior_votes + 5)

    headline = d[d["category"].isin(HEADLINE)]
    menu = (
        headline.groupby(["day", "meal"], sort=False)
        .agg(
            menu_pull_mean=("pull", "mean"),
            menu_pull_max=("pull", "max"),
            menu_rating=("rating", "mean"),
            n_headline=("pull", "size"),
        )
        .reset_index()
    )
    m = m.merge(menu, on=["day", "meal"], how="left")
    m[["menu_pull_mean", "menu_pull_max", "n_headline"]] = m[
        ["menu_pull_mean", "menu_pull_max", "n_headline"]
    ].fillna(0.0)
    m["menu_rating"] = m["menu_rating"].fillna(3.5)
    m["slow_dishes"] = (
        m[["day", "meal"]]
        .merge(d.groupby(["day", "meal"], sort=False)["slow"].sum().reset_index(), on=["day", "meal"], how="left")["slow"]
        .fillna(0)
        .astype(int)
        .to_numpy()
    )

    # Indicator columns for the linear model: which headline dishes are on, and meal x weekday.
    if len(headline):
        hot = pd.crosstab([headline["day"], headline["meal"]], headline["dish_id"]).clip(upper=1)
        hot.columns = [f"d_{int(dish_id)}" for dish_id in hot.columns]
        m = m.merge(hot.reset_index(), on=["day", "meal"], how="left")
        dish_columns = list(hot.columns)
        m[dish_columns] = m[dish_columns].fillna(0.0).astype(float)
    slot = "mw_" + m["meal"].astype(str) + "_" + m["weekday"].astype(str)
    slots = pd.get_dummies(slot).reindex(columns=MEAL_WEEKDAY_COLUMNS, fill_value=False).astype(float)
    m = pd.concat([m, slots], axis=1)
    return m


def dish_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column.startswith("d_")]


def portion_frame(meals: pd.DataFrame, dishes: pd.DataFrame) -> pd.DataFrame:
    """One row per dish per sitting. `take` (grams eaten per head / standard portion) is the target."""
    context = meals[["day", "meal", "served", "temp_c", "kind"]].copy()
    context["meal_idx"] = context["meal"].map(MEAL_INDEX).astype(int)
    d = dishes.merge(context, on=["day", "meal"], how="inner")
    d = d.sort_values(["day", "meal_idx", "dish_id"]).reset_index(drop=True)
    d["weekday"] = d["day"].dt.day_of_week.astype(int)
    d["cat_idx"] = d["category"].map({name: i for i, name in enumerate(CATEGORIES)}).fillna(0).astype(int)
    d["is_exam"] = (d["kind"] == "exam").astype(int)
    d["veg_i"] = d["veg"].astype(int)

    consumed = d["prepared_kg"] - d["leftover_kg"]
    d["consumed_kg"] = consumed
    # A pot that ran dry hides how much more people wanted. Dropping those sittings would teach the
    # model to cook less and less, so the take is measured among the diners who actually got the dish
    # (the kitchen logs how many went without). With no count logged, assume a typical shortfall.
    got_it = (d["served"] - d["short_heads"]).where(d["served"] > 0).clip(lower=1.0)
    d["take"] = consumed * 1000 / got_it / d["portion_g"]
    uncounted = d["ran_out"] & (d["short_heads"] <= 0)
    d["take"] = d["take"].where(~uncounted, d["take"] * UNCOUNTED_SHORTFALL)
    d["valid"] = d["take"].notna()
    # What the hall wanted in total, including the diners who went without.
    d["wanted_kg"] = d["take"] * d["portion_g"] * d["served"] / 1000

    sitting = [d["day"], d["meal"]]
    d["n_dishes"] = d.groupby(["day", "meal"], sort=False)["dish_id"].transform("size").astype(float)
    d["n_special"] = (d["category"] == "special").astype(float).groupby(sitting, sort=False).transform("sum")
    nonveg_main = ((~d["veg"]) & d["category"].isin(["special", "breakfast"])).astype(int)
    d["has_nonveg"] = nonveg_main.groupby(sitting, sort=False).transform("max")

    d["_v"] = d["take"].where(d["valid"], 0.0)
    d["_k"] = d["valid"].astype(float)
    grouped = d.groupby("dish_id", sort=False)
    prior_sum = grouped["_v"].cumsum() - d["_v"]
    prior_n = grouped["_k"].cumsum() - d["_k"]
    d["take_prior"] = (prior_sum + 2 * 0.85) / (prior_n + 2)
    d["take_n"] = np.minimum(prior_n, 30.0)
    return d.drop(columns=["_v", "_k"])
