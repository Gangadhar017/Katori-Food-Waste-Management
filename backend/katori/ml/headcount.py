"""Headcount forecast: how many residents will turn up for a sitting.

Two variants share this code. The *cook* model runs at the kitchen's cut-off, when skip
notices are final. Everyone who gave notice is a certain no-show, so it predicts the
turnout *among residents who did not give notice*; that keeps it sane on days when half
the hostel has gone home. The *outlook* model plans the week ahead without notices.

Candidates are scored by walk-forward backtest against two naive baselines, and the
prediction interval comes from the backtest's own out-of-sample errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..meals import MEALS
from .features import MEAL_WEEKDAY_COLUMNS, dish_columns

LEVELS = (0.02, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.98)
MIN_TRAIN_DAYS = 21
MIN_OFF_DAY_SITTINGS = 20
CANDIDATES = ("ridge", "hgb", "blend")
BASELINES = ("last_week", "four_week")
LABELS = {
    "ridge": "Ridge regression",
    "hgb": "Gradient boosting",
    "blend": "Blend of both",
    "last_week": "Same meal last week",
    "four_week": "4-week average",
}

# meal_idx and weekday must stay first: the boosted trees treat columns 0 and 1 as categories.
COMPACT = [
    "meal_idx", "weekday", "dom", "month_end", "is_holiday", "is_break", "is_exam", "is_fest",
    "rain_mm", "temp_c", "lag7", "lag14", "roll4w", "roll7d", "meal_mean",
    "menu_pull_mean", "menu_pull_max", "menu_rating", "skip_share",
]  # fmt: skip
OUTLOOK_DROPS = {"skip_share", "roll7d"}  # not known a week ahead

IMPORTANCE_GROUPS = {
    "Skip notices": ("skip_share",),
    "Menu of the day": ("menu_pull_mean", "menu_pull_max", "menu_rating", "d_"),
    "Meal and weekday": ("meal_idx", "weekday", "mw_"),
    "Recent turnout": ("lag7", "lag14", "roll4w", "roll7d", "meal_mean"),
    "Exams, holidays, fests": ("is_holiday", "is_break", "is_exam", "is_fest"),
    "Weather": ("rain_mm", "temp_c"),
    "Time of month": ("dom", "month_end"),
}


class NotEnoughData(Exception):
    """Raised when the log is too short to train and backtest honestly."""


def _matrix(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    return frame.reindex(columns=columns, fill_value=0.0).to_numpy(dtype=float)


def _pool(frame: pd.DataFrame, kind: str, strength: int) -> np.ndarray:
    """Residents who could still turn up: the whole roll, minus notices once those are final."""
    if kind == "headcount_cook":
        return np.maximum(strength - frame["skips"].to_numpy(dtype=float), 1.0)
    return np.full(len(frame), float(strength))


def is_off_day(frame: pd.DataFrame) -> pd.Series:
    return (frame["is_holiday"] + frame["is_break"]) > 0


@dataclass
class HeadcountArtifact:
    kind: str
    algorithm: str
    compact: list[str]
    linear: list[str]
    ridge: object
    hgb: object
    quantiles: dict[float, float]
    off_quantiles: dict[float, float] = field(default_factory=dict)

    def _rate(self, frame: pd.DataFrame) -> np.ndarray:
        parts = []
        if self.algorithm in {"ridge", "blend"}:
            parts.append(self.ridge.predict(_matrix(frame, self.linear)))
        if self.algorithm in {"hgb", "blend"}:
            parts.append(self.hgb.predict(_matrix(frame, self.compact)))
        return np.clip(np.mean(parts, axis=0), 0.01, 1.2)

    def predict_heads(self, frame: pd.DataFrame, strength: int) -> np.ndarray:
        return self._rate(frame) * _pool(frame, self.kind, strength)

    def quantile(self, level: float, *, off_day: bool = False) -> float:
        """Relative error at this level: actual / forecast - 1. Holidays and breaks get their own, wider band."""
        table = self.quantiles
        widen = 1.0
        if off_day:
            if self.off_quantiles:
                table = self.off_quantiles
            else:
                widen = 2.5
        levels = sorted(table)
        return float(np.interp(level, levels, [table[q] for q in levels])) * widen


def _fit(train: pd.DataFrame, target: np.ndarray, compact: list[str], linear: list[str], quick: bool):
    ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-1, 3, 9)))
    ridge.fit(_matrix(train, linear), target)
    hgb = HistGradientBoostingRegressor(
        max_iter=110 if quick else 220,
        learning_rate=0.06,
        max_depth=3,
        min_samples_leaf=6,
        l2_regularization=1.0,
        categorical_features=[0, 1],
        random_state=7,
    )
    hgb.fit(_matrix(train, compact), target)
    return ridge, hgb


def fold_windows(done: pd.DataFrame, n_folds: int) -> list[tuple[int, pd.Timestamp, pd.Timestamp]]:
    """Weekly test windows, newest first, each trained only on the days before it."""
    first, last = done["day"].min(), done["day"].max()
    windows = []
    for k in range(n_folds):
        end = last - pd.Timedelta(days=7 * k)
        start = end - pd.Timedelta(days=6)
        if (start - first).days < MIN_TRAIN_DAYS:
            break
        windows.append((k, start, end))
    return windows


def backtest(
    frame: pd.DataFrame, strength: int, kind: str, compact: list[str], linear: list[str], n_folds: int, quick: bool
) -> pd.DataFrame:
    done = frame[frame["ratio"].notna()]
    parts = []
    for fold, start, end in fold_windows(done, n_folds):
        train = done[done["day"] < start]
        test = done[(done["day"] >= start) & (done["day"] <= end)]
        if test.empty:
            continue
        target = train["served"].to_numpy(dtype=float) / _pool(train, kind, strength)
        ridge, hgb = _fit(train, target, compact, linear, quick)
        pool = _pool(test, kind, strength)
        out = test[["day", "meal", "served"]].copy()
        out["fold"] = fold
        out["off"] = is_off_day(test).to_numpy()
        out["ridge"] = np.clip(ridge.predict(_matrix(test, linear)), 0.01, 1.2) * pool
        out["hgb"] = np.clip(hgb.predict(_matrix(test, compact)), 0.01, 1.2) * pool
        out["blend"] = (out["ridge"] + out["hgb"]) / 2
        out["last_week"] = test["lag7"].to_numpy() * strength
        out["four_week"] = test["roll4w"].to_numpy() * strength
        parts.append(out)
    if not parts:
        raise NotEnoughData("need at least four weeks of logged sittings")
    return pd.concat(parts, ignore_index=True)


def _score(bt: pd.DataFrame, column: str) -> dict:
    if bt.empty:
        return {"mae": None, "mape": None, "bias": None}
    error = bt[column] - bt["served"]
    eaten = bt["served"] > 0
    return {
        "mae": round(float(error.abs().mean()), 2),
        "mape": round(float((error[eaten].abs() / bt.loc[eaten, "served"]).mean() * 100), 2),
        "bias": round(float(error.mean()), 2),
    }


def _quantiles(relative: pd.Series) -> dict[float, float]:
    return {level: float(np.quantile(relative, level)) for level in LEVELS}


def _importance(artifact: HeadcountArtifact, recent: pd.DataFrame, strength: int) -> list[dict]:
    """How much worse the forecast gets when a group of inputs is scrambled."""
    rng = np.random.default_rng(11)
    actual = recent["served"].to_numpy(dtype=float)
    base = np.abs(artifact.predict_heads(recent, strength) - actual).mean()
    rises = {}
    for label, prefixes in IMPORTANCE_GROUPS.items():
        columns = [
            c for c in recent.columns if any(c == p or (p.endswith("_") and c.startswith(p)) for p in prefixes)
        ]
        columns = [c for c in columns if c in artifact.compact or c in artifact.linear]
        if not columns:
            continue
        gains = []
        for _ in range(4):
            shuffled = recent.copy()
            order = rng.permutation(len(recent))
            shuffled[columns] = recent[columns].to_numpy()[order]
            if "skip_share" in columns:
                shuffled["skips"] = recent["skips"].to_numpy()[order]
            gains.append(np.abs(artifact.predict_heads(shuffled, strength) - actual).mean() - base)
        rises[label] = max(float(np.mean(gains)), 0.0)
    total = sum(rises.values()) or 1.0
    ranked = sorted(rises.items(), key=lambda item: -item[1])
    return [{"group": label, "share": round(rise / total, 3), "mae_rise": round(rise, 2)} for label, rise in ranked]


def train(frame: pd.DataFrame, strength: int, kind: str, *, n_folds: int = 6, quick: bool = False):
    """Backtest the candidates, keep the best, refit it on everything.

    Returns (artifact, metrics, detail, backtest predictions of the chosen candidate).
    """
    compact = [c for c in COMPACT if kind == "headcount_cook" or c not in OUTLOOK_DROPS]
    linear = [c for c in compact if c not in {"meal_idx", "weekday"}] + MEAL_WEEKDAY_COLUMNS + dish_columns(frame)
    bt = backtest(frame, strength, kind, compact, linear, n_folds, quick)

    scores = {name: _score(bt, name) for name in (*CANDIDATES, *BASELINES)}
    algorithm = min(CANDIDATES, key=lambda name: scores[name]["mae"])
    baseline = min(BASELINES, key=lambda name: scores[name]["mae"])

    # The band is sized on ordinary days; a break in the sample would otherwise stretch it for every day.
    relative = bt["served"] / bt[algorithm].clip(lower=1.0) - 1
    ordinary = ~bt["off"]
    quantiles = _quantiles(relative[ordinary] if ordinary.sum() >= 20 else relative)
    off_quantiles = _quantiles(relative[~ordinary]) if (~ordinary).sum() >= MIN_OFF_DAY_SITTINGS else {}
    coverage = None
    folds = sorted(bt["fold"].unique())
    if len(folds) >= 4:
        # Calibrate on older weeks, then count how often the newest two weeks fall inside the band.
        newest = bt["fold"].isin(folds[:2])
        if (ordinary & ~newest).sum() >= 20 and (ordinary & newest).sum() >= 10:
            low, high = np.quantile(relative[ordinary & ~newest], [0.1, 0.9])
            inside = (relative[ordinary & newest] >= low) & (relative[ordinary & newest] <= high)
            coverage = round(float(inside.mean()), 3)

    done = frame[frame["ratio"].notna()]
    target = done["served"].to_numpy(dtype=float) / _pool(done, kind, strength)
    ridge, hgb = _fit(done, target, compact, linear, quick)
    artifact = HeadcountArtifact(kind, algorithm, compact, linear, ridge, hgb, quantiles, off_quantiles)

    best, naive = scores[algorithm], scores[baseline]
    usual, unusual = _score(bt[ordinary], algorithm), _score(bt[~ordinary], algorithm)
    metrics = {
        **best,
        "baseline": baseline,
        "baseline_mae": naive["mae"],
        "skill": round(1 - best["mae"] / naive["mae"], 3) if naive["mae"] else 0.0,
        "ordinary_mae": usual["mae"],
        "ordinary_mape": usual["mape"],
        "ordinary_baseline_mae": _score(bt[ordinary], baseline)["mae"],
        "off_day_mae": unusual["mae"],
        "off_day_sittings": int((~ordinary).sum()),
        "coverage_80": coverage,
        "backtest_sittings": int(len(bt)),
        "backtest_weeks": int(len(folds)),
    }
    detail = {
        "candidates": [
            {"key": name, "label": LABELS[name], "baseline": name in BASELINES, **scores[name]}
            for name in (*CANDIDATES, *BASELINES)
        ],
        "quantiles": {str(level): round(value, 4) for level, value in quantiles.items()},
        "by_meal": {
            meal: round(float((bt.loc[bt["meal"] == meal, algorithm] - bt.loc[bt["meal"] == meal, "served"]).abs().mean()), 2)
            for meal in MEALS
            if (bt["meal"] == meal).any()
        },
    }
    if not quick:
        recent = done[done["day"] > done["day"].max() - pd.Timedelta(days=42)]
        detail["importance"] = _importance(artifact, recent, strength)

    chosen = bt[["day", "meal", "fold", "served", "off"]].copy()
    chosen["pred"] = bt[algorithm]
    return artifact, metrics, detail, chosen
