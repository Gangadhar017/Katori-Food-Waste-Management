"""Portion model: how much of each dish one diner really eats.

The target is the *take*: grams eaten per head divided by the dish's standard portion.
Multiplying head count by take gives the quantity to cook, and the safety margin on top
is calibrated on the joint error of both models (see `calibrate_demand`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .headcount import LEVELS, NotEnoughData, fold_windows

# dish_code, cat_idx and meal_idx must stay first: columns 0-2 are treated as categories.
FEATURES = [
    "dish_code", "cat_idx", "meal_idx", "weekday", "veg_i", "portion_g", "n_dishes", "n_special",
    "has_nonveg", "take_prior", "take_n", "temp_c", "is_exam",
]  # fmt: skip
CANDIDATES = ("dish_average", "hgb", "blend")
LABELS = {
    "dish_average": "Dish's own running average",
    "hgb": "Gradient boosting",
    "blend": "Blend of both",
    "standard": "Full standard portion",
}
MAX_DISH_CODES = 250  # the boosted trees bin categories into at most 255 values


def _matrix(frame: pd.DataFrame, codes: dict[int, int]) -> np.ndarray:
    data = frame.reindex(columns=FEATURES, fill_value=0.0).copy()
    data["dish_code"] = frame["dish_id"].map(codes).astype(float)  # unseen dishes become missing
    return data.to_numpy(dtype=float)


@dataclass
class PortionArtifact:
    algorithm: str
    dish_codes: dict[int, int]
    hgb: object
    demand_quantiles: dict[float, float] = field(default_factory=dict)

    def predict_take(self, frame: pd.DataFrame) -> np.ndarray:
        prior = frame["take_prior"].to_numpy(dtype=float)
        if self.algorithm == "dish_average":
            return prior
        boosted = self.hgb.predict(_matrix(frame, self.dish_codes))
        result = boosted if self.algorithm == "hgb" else (boosted + prior) / 2
        return np.clip(result, 0.05, 2.0)

    def margin(self, level: float) -> float:
        """Extra to cook on top of the expected quantity so a pot runs dry only (1 - level) of the time."""
        if not self.demand_quantiles:
            return 0.10
        levels = sorted(self.demand_quantiles)
        return float(np.interp(level, levels, [self.demand_quantiles[q] for q in levels]))


def _codes(train: pd.DataFrame) -> dict[int, int]:
    dish_ids = sorted(int(d) for d in train["dish_id"].unique())[:MAX_DISH_CODES]
    return {dish_id: code for code, dish_id in enumerate(dish_ids)}


def _fit(train: pd.DataFrame, quick: bool):
    codes = _codes(train)
    model = HistGradientBoostingRegressor(
        max_iter=120 if quick else 260,
        learning_rate=0.07,
        max_depth=4,
        min_samples_leaf=8,
        l2_regularization=0.5,
        categorical_features=[0, 1, 2],
        random_state=7,
    )
    model.fit(_matrix(train, codes), train["take"].to_numpy(dtype=float))
    return model, codes


def _kg_error(bt: pd.DataFrame, column: str) -> pd.Series:
    return (bt[column] - bt["take"]).abs() * bt["portion_g"] * bt["served"] / 1000


def train(frame: pd.DataFrame, *, n_folds: int = 6, quick: bool = False):
    """Returns (artifact, metrics, detail, backtest predictions of the chosen candidate)."""
    valid = frame[frame["valid"]]
    if valid.empty:
        raise NotEnoughData("no logged dish quantities yet")
    parts = []
    for fold, start, end in fold_windows(valid, n_folds):
        train_rows = valid[valid["day"] < start]
        test = valid[(valid["day"] >= start) & (valid["day"] <= end)]
        if test.empty or train_rows.empty:
            continue
        model, codes = _fit(train_rows, quick)
        out = test[["day", "meal", "dish_id", "served", "portion_g", "take", "habit_kg", "consumed_kg"]].copy()
        out["fold"] = fold
        out["dish_average"] = test["take_prior"].to_numpy()
        out["hgb"] = np.clip(model.predict(_matrix(test, codes)), 0.05, 2.0)
        out["blend"] = (out["dish_average"] + out["hgb"]) / 2
        out["standard"] = 1.0
        parts.append(out)
    if not parts:
        raise NotEnoughData("need at least four weeks of logged dish quantities")
    bt = pd.concat(parts, ignore_index=True)

    eaten_kg = float(bt["consumed_kg"].sum()) or 1.0
    scores = {}
    for name in (*CANDIDATES, "standard"):
        error = _kg_error(bt, name)
        scores[name] = {"mae": round(float(error.mean()), 3), "wape": round(float(error.sum() / eaten_kg * 100), 2)}
    algorithm = min(CANDIDATES, key=lambda name: scores[name]["mae"])

    model, codes = _fit(valid, quick)
    artifact = PortionArtifact(algorithm, codes, model)
    metrics = {
        **scores[algorithm],
        "baseline": "standard",
        "baseline_mae": scores["standard"]["mae"],
        "skill": round(1 - scores[algorithm]["mae"] / scores["standard"]["mae"], 3) if scores["standard"]["mae"] else 0.0,
        "backtest_rows": int(len(bt)),
    }
    detail = {
        "candidates": [
            {"key": name, "label": LABELS[name], "baseline": name == "standard", **scores[name]}
            for name in (*CANDIDATES, "standard")
        ]
    }
    chosen = bt[["day", "meal", "dish_id", "fold", "served", "portion_g", "take", "habit_kg"]].copy()
    chosen["pred_take"] = bt[algorithm]
    return artifact, metrics, detail, chosen


def calibrate_demand(head_bt: pd.DataFrame, portion_bt: pd.DataFrame, level: float):
    """Size the safety margin from how wrong the two models were *together*.

    Returns (quantiles of actual/predicted - 1, policy backtest). The policy backtest sets the
    margin on older weeks and then replays the newest two weeks: how much would have been left
    over, and how often a pot would have run dry, against the kitchen's old fixed rule.
    """
    joined = portion_bt.merge(
        head_bt[["day", "meal", "pred", "off"]].rename(columns={"pred": "head_pred"}), on=["day", "meal"], how="inner"
    )
    if joined.empty:
        return {}, {}
    joined["pred_kg"] = joined["head_pred"] * joined["pred_take"] * joined["portion_g"] / 1000
    joined["actual_kg"] = joined["served"] * joined["take"] * joined["portion_g"] / 1000
    joined = joined[joined["pred_kg"] > 0.05]
    # Size the margin on ordinary days: one break week would otherwise distort it for the whole year.
    if (~joined["off"]).sum() >= 40:
        joined = joined[~joined["off"]]
    relative = joined["actual_kg"] / joined["pred_kg"] - 1
    quantiles = {q: float(np.quantile(relative, q)) for q in LEVELS}

    policy: dict = {}
    folds = sorted(joined["fold"].unique())
    if len(folds) >= 4:
        newest = joined["fold"].isin(folds[:2])
        margin = float(np.quantile(relative[~newest], level))
        replay = joined[newest]
        advised = replay["pred_kg"] * (1 + margin)
        policy = {
            "weeks": 2,
            "sittings": int(replay[["day", "meal"]].drop_duplicates().shape[0]),
            "margin": round(margin, 4),
            "leftover_pct": round(float((advised - replay["actual_kg"]).clip(lower=0).sum() / advised.sum() * 100), 2),
            "runout_pct": round(float((replay["actual_kg"] > advised).mean() * 100), 2),
        }
        habit = replay[replay["habit_kg"].notna()]
        if len(habit):
            policy["habit_leftover_pct"] = round(
                float((habit["habit_kg"] - habit["actual_kg"]).clip(lower=0).sum() / habit["habit_kg"].sum() * 100), 2
            )
            policy["habit_runout_pct"] = round(float((habit["actual_kg"] > habit["habit_kg"]).mean() * 100), 2)
    return quantiles, policy
