"""The simulated hostel must be repeatable and behave like the hostel it claims to be."""

from datetime import date

from katori.catalog import DISH_BY_NAME, WEEKLY_CHART
from katori.sim import world


def _facts(names):
    return [world.DishFacts(n, DISH_BY_NAME[n].category, DISH_BY_NAME[n].veg, DISH_BY_NAME[n].portion_g) for n in names]


def test_same_day_always_plays_out_the_same():
    day, dishes = date(2026, 9, 2), _facts(WEEKLY_CHART[2]["dinner"])
    context = world.day_context(7, day)
    first = world.meal_truth(7, day, "dinner", dishes, context, 400)
    again = world.meal_truth(7, day, "dinner", dishes, context, 400)
    assert first == again
    assert world.meal_truth(8, day, "dinner", dishes, world.day_context(8, day), 400) != first


def test_popular_menu_draws_a_bigger_crowd():
    day = date(2026, 9, 3)  # an ordinary Thursday
    context = world.day_context(7, day)
    liked = world.turnout_rate("dinner", day, context, _facts(["Roti", "Paneer Butter Masala"]))
    disliked = world.turnout_rate("dinner", day, context, _facts(["Roti", "Tinda Masala"]))
    assert liked > disliked + 0.1


def test_hostel_empties_over_diwali_and_most_people_give_notice():
    kind, label, present = world.calendar_for(date(2026, 11, 8))
    assert (kind, label) == ("break", "Diwali break") and present < 0.5
    day, dishes = date(2026, 11, 8), _facts(WEEKLY_CHART[6]["lunch"])
    truth = world.meal_truth(7, day, "lunch", dishes, world.day_context(7, day), 400)
    assert truth.served < 160
    assert truth.skips > 200  # the notices are what lets the cook sheet see the break coming


def test_swaps_stay_within_the_dish_family():
    chart = {meal: list(names) for meal, names in WEEKLY_CHART[1].items()}
    swapped = 0
    for offset in range(60):
        day = date(2026, 8, 4 + offset % 27)
        menu = world.menu_with_swaps(offset, day, chart)
        for meal, names in menu.items():
            assert len(names) == len(chart[meal]) == len(set(names))
            for before, after in zip(chart[meal], names, strict=True):
                if before != after:
                    swapped += 1
                    assert DISH_BY_NAME[before].category == DISH_BY_NAME[after].category
                    assert DISH_BY_NAME[before].veg == DISH_BY_NAME[after].veg
    assert swapped > 10


def test_a_third_counter_shortens_the_wait():
    day = date(2026, 9, 3)
    two = world.simulate_line(7, day, "dinner", 330, 2, 0, 120)
    three = world.simulate_line(7, day, "dinner", 330, 3, 0, 120)
    assert len(two) == len(three) == 330
    assert all(wait >= 0 for _, _, wait in two)
    assert sum(w for _, _, w in three) < sum(w for _, _, w in two) * 0.7
