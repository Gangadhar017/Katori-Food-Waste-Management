"""Ground truth of the simulated hostel.

This module decides how many residents really turn up and how much they really eat.
The forecasting code never imports it: models only see what a kitchen would log
(menus, the calendar, skip notices, head counts, weights). Everything is a pure
function of (seed, date, meal), so the same day always plays out the same way.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from ..catalog import DISH_BY_NAME, DISHES

# How much residents like each dish, from -1 (avoided) to +1 (queue out the door).
APPEAL: dict[str, float] = {
    "Aloo Paratha": 0.55, "Poha": 0.10, "Idli Sambar": 0.30, "Masala Dosa": 0.80, "Chole Bhature": 0.85,
    "Upma": -0.45, "Bread Omelette": 0.50, "Puri Bhaji": 0.45, "Veg Sandwich": 0.0, "Daliya": -0.70,
    "Veg Pulao": 0.30, "Veg Biryani": 0.60, "Chicken Biryani": 0.95,
    "Dal Tadka": 0.20, "Dal Makhani": 0.60, "Rajma": 0.70, "Chole": 0.50, "Kadhi Pakora": 0.25, "Sambar": 0.0,
    "Aloo Gobi": 0.10, "Mix Veg": -0.20, "Lauki Chana": -0.75, "Tinda Masala": -0.85, "Bhindi Fry": 0.30,
    "Baingan Bharta": -0.40, "Aloo Matar": 0.15, "Cabbage Matar": -0.50,
    "Palak Paneer": 0.60, "Paneer Butter Masala": 0.90, "Kadhai Paneer": 0.80, "Matar Paneer": 0.65,
    "Soya Chaap Masala": 0.40, "Egg Curry": 0.55, "Chicken Curry": 0.90,
    "Gulab Jamun": 0.80, "Kheer": 0.50, "Suji Halwa": 0.35, "Ice Cream": 0.85, "Fruit Custard": 0.55,
    "Samosa": 0.75, "Veg Pakora": 0.50, "Maggi": 0.90, "Bread Pakora": 0.45, "Aloo Tikki": 0.50,
    "Veg Cutlet": 0.20, "Bhel Puri": 0.35, "Vada Pav": 0.60, "Sprouts Chaat": -0.50, "Biscuits": -0.30,
}  # fmt: skip

# Share of a standard portion actually eaten, where it is not driven by appeal.
_TAKE: dict[str, float] = {
    "Steamed Rice": 0.72, "Roti": 0.90, "Jeera Rice": 0.76, "Tea": 0.80, "Milk": 0.45, "Banana": 0.55,
    "Boiled Egg": 0.50, "Salad": 0.50, "Curd": 0.60, "Boondi Raita": 0.62,
}  # fmt: skip

BASE_RATE = {"breakfast": 0.60, "lunch": 0.80, "snacks": 0.52, "dinner": 0.85}
WEEKDAY_SHIFT = {
    "breakfast": (0, 0, 0, 0, 0, -0.12, -0.14),
    "lunch": (0, 0, 0, 0, -0.01, -0.05, -0.02),
    "snacks": (0, 0, 0, 0, -0.04, -0.10, -0.08),
    "dinner": (0, 0, 0, 0, -0.08, -0.12, -0.03),
}
# What the kitchen assumed before it had numbers: a fixed share of the roll, every day.
HABIT_RATE = {"breakfast": 0.70, "lunch": 0.86, "snacks": 0.62, "dinner": 0.90}
AWAY_NOTICE_RATE = 0.88  # going home is marked for the whole stay with one tap, so nearly everyone does
PLATE_WASTE_G = {"breakfast": 22.0, "lunch": 40.0, "snacks": 12.0, "dinner": 42.0}
PREP_WASTE_SHARE = {
    "breakfast": 0.03, "staple": 0.01, "dal": 0.02, "sabzi": 0.09, "special": 0.04,
    "snack": 0.03, "side": 0.08, "dessert": 0.01, "beverage": 0.01,
}  # fmt: skip

FIXED_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (1, 26): "Republic Day",
    (8, 15): "Independence Day",
    (10, 2): "Gandhi Jayanti",
    (12, 25): "Christmas",
}
FESTIVALS = {
    date(2026, 3, 4): "Holi",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 8): "Diwali",
    date(2027, 3, 22): "Holi",
    date(2027, 10, 9): "Dussehra",
    date(2027, 10, 29): "Diwali",
}


@dataclass(frozen=True)
class DishFacts:
    name: str
    category: str
    veg: bool
    portion_g: float
    slow: bool = False


@dataclass(frozen=True)
class DayContext:
    kind: str  # "" | holiday | break | exam | fest
    label: str
    present: float  # share of residents on campus
    temp_c: float
    rain_mm: float


@dataclass(frozen=True)
class MealTruth:
    served: int
    skips: int
    demand_kg: dict[str, float]
    plate_waste_kg: float
    ratings: dict[str, tuple[float, int]]  # dish -> (sum of stars, number of ratings)


def rng_for(seed: int, *parts: object) -> np.random.Generator:
    key = "|".join([str(seed), *map(str, parts)]).encode()
    return np.random.default_rng(int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big"))


def _between(day: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    return start <= (day.month, day.day) <= end


def calendar_for(day: date) -> tuple[str, str, float]:
    """Academic calendar: (kind, label, share of residents on campus)."""
    if _between(day, (5, 25), (7, 14)):
        return "break", "Summer break", 0.22
    if _between(day, (12, 19), (12, 31)) or _between(day, (1, 1), (1, 3)):
        return "break", "Winter break", 0.25
    for festival_day, name in FESTIVALS.items():
        gap = (day - festival_day).days
        if name == "Diwali":
            if abs(gap) <= 2:
                return "break", "Diwali break", 0.30
            if abs(gap) == 3:
                return "holiday", "Diwali travel day", 0.62
        elif name == "Holi" and gap in (-1, 0):
            return "holiday", "Holi", 0.55
        elif name == "Dussehra" and gap == 0:
            return "holiday", "Dussehra", 0.60
    if _between(day, (9, 21), (9, 27)) or _between(day, (3, 8), (3, 14)):
        return "exam", "Mid-semester exams", 1.0
    if _between(day, (12, 1), (12, 14)) or _between(day, (5, 8), (5, 22)):
        return "exam", "End-semester exams", 1.0
    if _between(day, (9, 11), (9, 13)):
        return "fest", "Freshers' fest", 1.0
    if _between(day, (2, 12), (2, 14)):
        return "fest", "Cultural fest", 1.0
    label = FIXED_HOLIDAYS.get((day.month, day.day))
    if label:
        return "holiday", label, 0.78
    return "", "", 1.0


def weather_for(seed: int, day: date) -> tuple[float, float]:
    """Daily mean temperature (C) and rainfall (mm) for a hot, dry North Indian city."""
    rng = rng_for(seed, "weather", day.isoformat())
    day_of_year = day.timetuple().tm_yday
    temp = 25.0 + 9.5 * math.cos(2 * math.pi * (day_of_year - 160) / 365) + rng.normal(0, 1.8)
    monsoon = _between(day, (6, 25), (9, 20))
    rain = float(rng.exponential(11.0)) if rng.random() < (0.38 if monsoon else 0.035) else 0.0
    if rain:
        temp -= min(4.0, rain / 6)
    return round(float(temp), 1), round(rain, 1)


def day_context(seed: int, day: date) -> DayContext:
    kind, label, present = calendar_for(day)
    temp, rain = weather_for(seed, day)
    return DayContext(kind, label, present, temp, rain)


def meal_appeal(dishes: Sequence[DishFacts]) -> float:
    values = [APPEAL.get(d.name, 0.0) for d in dishes if d.category not in {"beverage", "side", "staple"}]
    if not values:
        return 0.0
    return 0.6 * max(values) + 0.4 * (sum(values) / len(values))


def turnout_rate(meal: str, day: date, context: DayContext, dishes: Sequence[DishFacts]) -> float:
    rate = BASE_RATE[meal] + WEEKDAY_SHIFT[meal][day.weekday()] + 0.11 * meal_appeal(dishes)
    if context.kind == "exam":
        rate += 0.09 if meal == "breakfast" else 0.05  # nobody leaves campus, everyone is up early
    if context.kind == "fest" and meal in {"snacks", "dinner"}:
        rate -= 0.11  # food stalls on the lawns
    if context.rain_mm > 4 and meal in {"snacks", "dinner"}:
        rate += 0.04  # too wet to eat out
    if context.temp_c > 34 and meal == "lunch":
        rate -= 0.03
    if day.day >= 25:
        rate += 0.03  # month-end wallets
    return min(max(rate, 0.05), 0.97)


def expected_take(dish: DishFacts, dishes: Sequence[DishFacts]) -> float:
    """Share of a standard portion the average diner takes of this dish."""
    take = _TAKE.get(dish.name, 0.86 + 0.22 * APPEAL.get(dish.name, 0.0))
    nonveg_special = any(not d.veg and d.category == "special" for d in dishes)
    veg_special = any(d.veg and d.category == "special" for d in dishes)
    if dish.category == "special":
        if not dish.veg:
            take *= 0.56 if veg_special else 0.70
        elif nonveg_special:
            take *= 0.52
    elif dish.category == "breakfast" and not dish.veg:
        take *= 0.78
    return take


def on_campus(strength: int, day: date, context: DayContext) -> int:
    weekend = {5: 0.93, 6: 0.91}.get(day.weekday(), 1.0) if context.kind in {"", "exam", "fest"} else 1.0
    return int(round(strength * context.present * weekend))


def meal_truth(
    seed: int, day: date, meal: str, dishes: Sequence[DishFacts], context: DayContext, strength: int
) -> MealTruth:
    rng = rng_for(seed, "meal", day.isoformat(), meal)
    present = on_campus(strength, day, context)
    rate = turnout_rate(meal, day, context, dishes)
    served = int(rng.binomial(present, rate) * rng.lognormal(0, 0.022))
    served = max(0, min(served, present))

    # People who are away mostly say so; people who simply do not feel like it mostly do not.
    away, not_hungry = strength - present, present - served
    notice_rate = float(np.clip(rng.normal(0.36, 0.05), 0.05, 0.9))
    skips = int(rng.binomial(away, AWAY_NOTICE_RATE) + rng.binomial(not_hungry, notice_rate))

    demand = {
        d.name: served * d.portion_g * expected_take(d, dishes) * float(rng.lognormal(0, 0.055)) / 1000 for d in dishes
    }
    appeal = meal_appeal(dishes)
    plate_waste = served * PLATE_WASTE_G[meal] * (1 - 0.45 * appeal) * float(rng.lognormal(0, 0.10)) / 1000

    ratings: dict[str, tuple[float, int]] = {}
    for d in dishes:
        if d.category in {"beverage", "staple"}:
            continue
        count = int(rng.binomial(served, 0.09)) if served else 0
        mean = float(np.clip(3.15 + 1.45 * APPEAL.get(d.name, 0.0) + rng.normal(0, 0.18), 1.2, 4.9))
        ratings[d.name] = (round(mean * count, 1), count)
    return MealTruth(served, skips, demand, round(plate_waste, 2), ratings)


def habit_kg(dish: DishFacts, dishes: Sequence[DishFacts], meal: str, strength: int, context: DayContext) -> float:
    """What the kitchen cooked by rule of thumb: a fixed share of the roll plus a comfort margin."""
    crowd = strength * HABIT_RATE[meal] * context.present**0.6
    return round(crowd * dish.portion_g * expected_take(dish, dishes) * 1.10 / 1000, 1)


def prep_waste_kg(seed: int, day: date, meal: str, prepared: dict[str, float], dishes: Sequence[DishFacts]) -> float:
    rng = rng_for(seed, "prep", day.isoformat(), meal)
    total = sum(prepared.get(d.name, 0.0) * PREP_WASTE_SHARE.get(d.category, 0.03) for d in dishes)
    return round(total * float(rng.lognormal(0, 0.12)), 2)


def skips_declared_by(final_skips: int, hours_to_cutoff: float) -> int:
    """Skip notices trickle in over the 30 hours before the kitchen's cut-off."""
    share = min(max(1 - hours_to_cutoff / 30, 0.0), 1.0)
    return int(final_skips * share)


def _pool_key(name: str) -> str | None:
    spec = DISH_BY_NAME.get(name)
    if spec is None or "Biryani" in name:
        return None
    if spec.category not in {"breakfast", "snack", "dal", "sabzi", "special", "dessert"}:
        return None
    # A vegetarian dish is only ever replaced by another vegetarian one, so nobody is left without a main.
    return f"{spec.category}:{'veg' if spec.veg else 'nonveg'}"


_POOLS: dict[str, list[str]] = {}
for _spec in DISHES:
    _key = _pool_key(_spec.name)
    if _key:
        _POOLS.setdefault(_key, []).append(_spec.name)


def menu_with_swaps(seed: int, day: date, chart: dict[str, Sequence[str]], swap_chance: float = 0.24) -> dict[str, list[str]]:
    """The day's menu: the weekly chart, with the odd substitution a real kitchen makes."""
    menu: dict[str, list[str]] = {}
    for meal, names in chart.items():
        names = list(names)
        rng = rng_for(seed, "menu", day.isoformat(), meal)
        if rng.random() < swap_chance:
            swappable = [i for i, name in enumerate(names) if _pool_key(name)]
            if swappable:
                slot = int(rng.choice(swappable))
                options = [n for n in _POOLS[_pool_key(names[slot])] if n not in names]
                if options:
                    names[slot] = str(rng.choice(options))
        menu[meal] = names
    return menu


# --- The serving line -------------------------------------------------------------------------

SERVICE_SECONDS = 17.0  # mean time to plate one person at one counter
SLOW_DISH_SECONDS = 12.0  # extra per made-to-order dish on the menu
SERVICE_SIGMA = 0.35


def service_seconds(rng: np.random.Generator, slow_dishes: int) -> float:
    mean = SERVICE_SECONDS + SLOW_DISH_SECONDS * slow_dishes
    return float(rng.lognormal(math.log(mean) - SERVICE_SIGMA**2 / 2, SERVICE_SIGMA))


def simulate_line(
    seed: int, day: date, meal: str, people: int, counters: int, slow_dishes: int, minutes: float
) -> list[tuple[float, int, float]]:
    """Play out one sitting's queue. Returns (minute joined, people ahead, seconds waited) per diner."""
    rng = rng_for(seed, "line", day.isoformat(), meal)
    if people <= 0:
        return []
    # Most of the hall arrives in a rush shortly after the counter opens.
    arrivals = np.sort(np.clip(rng.gamma(2.2, minutes * 60 / 6.5, size=people), 0, minutes * 60 * 0.97))
    free_at = [0.0] * counters
    start_times: list[float] = []
    results: list[tuple[float, int, float]] = []
    for arrival in arrivals:
        counter = min(range(counters), key=free_at.__getitem__)
        start = max(arrival, free_at[counter])
        free_at[counter] = start + service_seconds(rng, slow_dishes)
        ahead = sum(1 for s in start_times[-80:] if s > arrival)
        start_times.append(start)
        results.append((arrival / 60, ahead, start - arrival))
    return results


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())
