"""Forecasting: no peeking at the future, better than naive, and a gate that can say no."""

import pandas as pd
from sqlalchemy import select

from katori.ml import pipeline, registry
from katori.ml.features import headcount_frame, load_dishes, load_meals, portion_frame
from katori.models import DishService, MealService, ModelRun

from .conftest import STRENGTH

FEATURES = ["lag7", "lag14", "roll4w", "roll7d", "meal_mean", "menu_pull_mean", "menu_pull_max", "menu_rating"]


def test_features_of_a_sitting_never_use_that_sitting_or_later_ones(db, tenant):
    meals, dishes = load_meals(db, tenant.id), load_dishes(db, tenant.id)
    frame = headcount_frame(meals, dishes, STRENGTH)
    done = frame[frame["ratio"].notna()]
    cut = done["day"].max() - pd.Timedelta(days=10)

    # Rewrite everything from the cut onwards; features of that day and earlier must not move.
    tampered_meals, tampered_dishes = meals.copy(), dishes.copy()
    tampered_meals.loc[tampered_meals["day"] >= cut, "served"] = 1.0
    tampered_dishes.loc[tampered_dishes["day"] >= cut, ["rating_sum", "rating_n"]] = [5.0, 1.0]
    tampered = headcount_frame(tampered_meals, tampered_dishes, STRENGTH)

    before = frame[frame["day"] <= cut][FEATURES].reset_index(drop=True)
    after = tampered[tampered["day"] <= cut][FEATURES].reset_index(drop=True)
    pd.testing.assert_frame_equal(before, after)


def test_portion_target_counts_the_diners_who_went_without(db, tenant):
    meals, dishes = load_meals(db, tenant.id), load_dishes(db, tenant.id)
    frame = portion_frame(meals, dishes)
    dry = frame[frame["ran_out"] & (frame["short_heads"] > 0)]
    assert len(dry) > 0, "the simulated kitchen should have run out of something at least once"
    # What the hall wanted is more than what the pot held.
    assert (dry["wanted_kg"] > dry["consumed_kg"]).all()
    assert frame.loc[frame["prepared_kg"].notna(), "valid"].all()


def test_serving_models_beat_their_naive_baselines(db, tenant):
    for kind in ("headcount_cook", "headcount_outlook", "portion", "wait"):
        run = registry.champion(db, tenant.id, kind)
        assert run is not None, f"no serving model for {kind}"
        assert run.metrics["mae"] <= run.metrics["baseline_mae"], kind
        assert registry.load(run) is not None
    cook = registry.champion(db, tenant.id, "headcount_cook")
    assert cook.metrics["skill"] > 0.2
    assert cook.metrics["mape"] < 12


def test_every_live_forecast_was_written_before_its_sitting(db, tenant):
    scored = db.scalars(
        select(MealService).where(MealService.tenant_id == tenant.id, MealService.served.is_not(None), MealService.forecast_p50.is_not(None))
    ).all()
    assert len(scored) > 50
    assert all(s.forecast_model.startswith("cook") for s in scored)
    assert all(s.forecast_at <= s.logged_at for s in scored)
    assert all(s.forecast_p10 <= s.forecast_p50 <= s.forecast_p90 for s in scored)


def test_gate_refuses_a_model_that_loses_to_the_baseline(db, tenant):
    promote, verdict = pipeline._gate(db, tenant, "portion", {"mae": 5.0, "baseline_mae": 4.0, "baseline": "standard"}, None, None)
    assert not promote and "naive baseline" in verdict
    promote, _ = pipeline._gate(db, tenant, "portion", {"mae": 3.0, "baseline_mae": 4.0, "baseline": "standard"}, None, None)
    assert promote


def test_gate_keeps_the_serving_model_when_the_challenger_is_worse_on_new_sittings(db, tenant):
    current = registry.champion(db, tenant.id, "headcount_cook")
    meals = load_meals(db, tenant.id)
    # Pretend the serving model was trained two weeks ago and has been scored live since.
    original = current.train_through
    current.train_through = original - pd.Timedelta(days=14)
    live = meals[(meals["day"] > pd.Timestamp(current.train_through)) & meals["served"].notna() & meals["forecast_p50"].notna()]
    challenger = live[["day", "meal"]].copy()
    challenger["pred"] = live["served"] + 60  # far worse than what is serving
    metrics = {"mae": 1.0, "baseline_mae": 2.0, "baseline": "four_week"}
    promote, verdict = pipeline._gate(db, tenant, "headcount_cook", metrics, challenger, meals)
    current.train_through = original
    db.rollback()
    assert not promote and "serving model was more accurate" in verdict
    assert metrics["live_challenger_mae"] > metrics["live_serving_mae"]


def test_registry_keeps_one_serving_model_per_kind(db, tenant):
    runs = db.scalars(select(ModelRun).where(ModelRun.tenant_id == tenant.id)).all()
    for kind in {run.kind for run in runs}:
        assert sum(1 for run in runs if run.kind == kind and run.status == "champion") == 1
    assert any(run.status == "retired" for run in runs)
    assert all(run.path == "" for run in runs if run.status != "champion")


def test_cooking_from_the_sheet_leaves_less_in_the_pots(db, tenant):
    rows = db.execute(
        select(MealService.mode, DishService.prepared_kg, DishService.leftover_kg)
        .join(DishService, (DishService.tenant_id == MealService.tenant_id) & (DishService.day == MealService.day) & (DishService.meal == MealService.meal))
        .where(MealService.tenant_id == tenant.id, MealService.served.is_not(None), MealService.calendar_kind == "")
    ).all()
    share = {}
    for mode in ("habit", "katori"):
        cooked = sum(r.prepared_kg for r in rows if r.mode == mode)
        left = sum(r.leftover_kg for r in rows if r.mode == mode)
        share[mode] = left / cooked
    assert share["katori"] < share["habit"] * 0.9
