from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from importlib.metadata import version as package_version
from typing import Any

XGBOOST_IMPLEMENTATION_VERSION = f"xgboost-{package_version('xgboost-cpu')}"
XGBOOST_RECIPE_VERSION = "shallow-hist-v1"
XGBOOST_TRAINING_SEED = 1947
XGBOOST_MINIMUM_TRAINING_SAMPLES = 250
XGBOOST_ROUNDS = 64
XGBOOST_PARAMETERS: dict[str, int | float | str] = {
    "objective": "reg:squarederror",
    "tree_method": "hist",
    "max_depth": 3,
    "eta": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 8,
    "reg_lambda": 10.0,
    "reg_alpha": 0.05,
    "max_bin": 64,
    "seed": XGBOOST_TRAINING_SEED,
    "nthread": 1,
    "verbosity": 0,
}


def fit_xgboost(
    rows: Sequence[Sequence[float]],
    outcomes: Sequence[float],
) -> bytes | None:
    """Fit the one predeclared CPU recipe and return portable model JSON."""

    if len(rows) < XGBOOST_MINIMUM_TRAINING_SAMPLES or len(rows) != len(outcomes):
        return None
    width = len(rows[0]) if rows else 0
    if width < 1 or any(len(row) != width for row in rows):
        return None
    if any(not math.isfinite(float(value)) for row in rows for value in row):
        return None
    if any(not math.isfinite(float(value)) for value in outcomes):
        return None
    # Keep the heavier numerical stack out of ordinary Baseline-only startup. It is loaded only
    # inside the one quiet-time worker after the nonlinear evidence floor has actually been met.
    try:
        import numpy as np
        import xgboost as xgb
    except (ImportError, OSError):
        return None

    features = np.asarray(rows, dtype=np.float32)
    targets = np.clip(np.asarray(outcomes, dtype=np.float32), -1.0, 3.0)
    weights = np.asarray(
        [0.5 ** ((len(rows) - 1 - index) / 500) for index in range(len(rows))],
        dtype=np.float32,
    )
    matrix = xgb.DMatrix(features, label=targets, weight=weights)
    try:
        booster = xgb.train(
            dict(XGBOOST_PARAMETERS),
            matrix,
            num_boost_round=XGBOOST_ROUNDS,
        )
    except xgb.core.XGBoostError:
        return None
    payload = bytes(booster.save_raw(raw_format="json"))
    return payload or None


def load_xgboost(payload: bytes) -> Any:
    """Load application-owned JSON after the database has verified size and digest."""

    if not payload:
        raise ValueError("empty XGBoost payload")
    try:
        import xgboost as xgb
    except (ImportError, OSError) as exc:
        raise ValueError("XGBoost runtime is unavailable") from exc

    booster = xgb.Booster()
    try:
        booster.load_model(bytearray(payload))
    except xgb.core.XGBoostError as exc:
        raise ValueError("invalid XGBoost payload") from exc
    return booster


def predict_xgboost(
    booster: Any,
    rows: Sequence[Sequence[float]],
) -> list[float]:
    if not rows:
        return []
    width = len(rows[0])
    if width < 1 or any(len(row) != width for row in rows):
        raise ValueError("XGBoost prediction rows have inconsistent width")
    if any(not math.isfinite(float(value)) for row in rows for value in row):
        raise ValueError("XGBoost prediction rows contain non-finite values")
    try:
        import numpy as np
        import xgboost as xgb
    except (ImportError, OSError) as exc:
        raise ValueError("XGBoost runtime is unavailable") from exc

    try:
        predictions = booster.predict(xgb.DMatrix(np.asarray(rows, dtype=np.float32)))
    except xgb.core.XGBoostError as exc:
        raise ValueError("XGBoost prediction failed") from exc
    values = [float(value) for value in predictions]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("XGBoost prediction returned a non-finite value")
    return [max(-1.0, min(10.0, value)) for value in values]


def xgboost_payload_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def xgboost_metadata() -> dict[str, Any]:
    return {
        "implementation_version": XGBOOST_IMPLEMENTATION_VERSION,
        "recipe_version": XGBOOST_RECIPE_VERSION,
        "training_seed": XGBOOST_TRAINING_SEED,
        "minimum_training_samples": XGBOOST_MINIMUM_TRAINING_SAMPLES,
        "rounds": XGBOOST_ROUNDS,
        "hyperparameters": dict(XGBOOST_PARAMETERS),
        "payload_format": "json",
        "device": "cpu",
    }
