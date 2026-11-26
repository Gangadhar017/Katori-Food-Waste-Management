"""Wait-time model: how long until a resident who joins the line now is served."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..meals import MEAL_INDEX
from ..models import WaitSample
from .headcount import NotEnoughData

FEATURES = ["ahead", "counters", "slow_dishes", "minute", "meal_idx", "ahead_per_counter"]
MIN_SAMPLES = 400


def naive_wait(ahead: int, counters: int, seconds_per_person: float = 20.0) -> float:
    """People ahead times an average plating time, shared over the open counters."""
    return ahead * seconds_per_person / max(counters, 1)


@dataclass
class WaitArtifact:
    algorithm: str  # hgb | per_person
    model: object
    seconds_per_person: float
    spread_s: float  # 80th percentile of (actual - predicted)

    def predict(self, ahead: int, counters: int, slow_dishes: int, minute: float, meal: str) -> tuple[float, float]:
        """Returns (expected seconds, seconds by which 4 in 5 people are served)."""
        if ahead <= 0:
            return 0.0, 0.0
        if self.algorithm == "hgb":
            row = [[ahead, counters, slow_dishes, minute, MEAL_INDEX.get(meal, 0), ahead / max(counters, 1)]]
            expected = float(self.model.predict(np.asarray(row, dtype=float))[0])
        else:
            expected = naive_wait(ahead, counters, self.seconds_per_person)
        expected = max(expected, 0.0)
        return expected, expected + max(self.spread_s, 0.0)


def load_samples(db: Session, tenant_id: int) -> pd.DataFrame:
    rows = db.execute(
        select(
            WaitSample.day,
            WaitSample.meal,
            WaitSample.minute,
            WaitSample.ahead,
            WaitSample.counters,
            WaitSample.slow_dishes,
            WaitSample.wait_s,
        ).where(WaitSample.tenant_id == tenant_id)
    ).all()
    frame = pd.DataFrame(rows, columns=["day", "meal", "minute", "ahead", "counters", "slow_dishes", "wait_s"])
    frame["day"] = pd.to_datetime(frame["day"])
    frame["meal_idx"] = frame["meal"].map(MEAL_INDEX).astype(float)
    frame["ahead_per_counter"] = frame["ahead"] / frame["counters"].clip(lower=1)
    return frame


def train(samples: pd.DataFrame, *, quick: bool = False):
    """Returns (artifact, metrics, detail). The newest fifth of days is held out for scoring."""
    if len(samples) < MIN_SAMPLES:
        raise NotEnoughData("not enough finished waits to learn from")
    days = np.sort(samples["day"].unique())
    split = days[max(int(len(days) * 0.8) - 1, 0)]
    train_rows, test = samples[samples["day"] <= split], samples[samples["day"] > split]
    if test.empty or train_rows.empty:
        raise NotEnoughData("need waits from several days")

    def fit(rows: pd.DataFrame):
        model = HistGradientBoostingRegressor(
            max_iter=90 if quick else 180, learning_rate=0.08, max_depth=4, min_samples_leaf=20, random_state=7
        )
        model.fit(rows[FEATURES].to_numpy(dtype=float), rows["wait_s"].to_numpy(dtype=float))
        load = rows["ahead_per_counter"].to_numpy(dtype=float)
        per_person = float((load * rows["wait_s"]).sum() / max((load * load).sum(), 1e-9))
        return model, per_person

    model, per_person = fit(train_rows)
    boosted = model.predict(test[FEATURES].to_numpy(dtype=float))
    simple = test["ahead_per_counter"].to_numpy(dtype=float) * per_person
    actual = test["wait_s"].to_numpy(dtype=float)
    scores = {
        "hgb": round(float(np.abs(boosted - actual).mean()), 1),
        "per_person": round(float(np.abs(simple - actual).mean()), 1),
    }
    algorithm = min(scores, key=scores.get)
    residual = actual - (boosted if algorithm == "hgb" else simple)

    final_model, final_per_person = fit(samples)
    artifact = WaitArtifact(algorithm, final_model, final_per_person, float(np.quantile(residual, 0.8)))
    metrics = {
        "mae": scores[algorithm],
        "baseline": "per_person",
        "baseline_mae": scores["per_person"],
        "skill": round(1 - scores[algorithm] / scores["per_person"], 3) if scores["per_person"] else 0.0,
        "test_waits": int(len(test)),
    }
    detail = {
        "candidates": [
            {"key": "hgb", "label": "Gradient boosting", "baseline": False, "mae": scores["hgb"]},
            {"key": "per_person", "label": "People ahead x average plating time", "baseline": True, "mae": scores["per_person"]},
        ],
        "seconds_per_person": round(final_per_person, 1),
    }
    return artifact, metrics, detail
