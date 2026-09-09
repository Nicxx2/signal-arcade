"""Versioned entry-context Exit timing: small, immutable, and bounded to normal reviews.

Checkpoint returns are a timing comparison, not a replay of the adaptive execution policy.
Selection happens before outcomes exist. Live execution still uses all Baseline exit rules.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..models import RISK_LIMITS, ChallengerSkill, ChallengerSkillArtifact, RiskMode

IMPLEMENTATION = "entry-context-exit-ridge-v1"
RECIPE = "exit-context-v1"
ACTIVATION_POLICY = "independent-exit-context-v2"
PLAN_SCHEMA: Literal["entry-exit-plan-v1"] = "entry-exit-plan-v1"
FEATURES = (
    "opportunity",
    "danger",
    "confidence",
    "buy_ratio",
    "wallet_breadth",
    "concentration",
    "curve_progress",
    "momentum",
    "drawdown",
    "reserve_depth",
)
HORIZONS = (60, 300, 600, 900, 1200)
MINIMUM_PREDICTED_EDGE = 0.01
SUPPORT_Z = 6.0


class ExitTimingPlan(BaseModel):
    """A saved recommendation is provenance, never permission to influence trading."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal["entry-exit-plan-v1"] = PLAN_SCHEMA
    decision_id: str = Field(min_length=1, max_length=256)
    artifact_version: str = Field(min_length=1, max_length=512)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_horizon_seconds: int = Field(strict=True, ge=60, le=1200)
    created_at: datetime
    risk_mode: RiskMode
    configuration_fingerprint: str
    baseline_version: str
    feature_schema_version: str
    joined_at: str
    dependency_epochs: dict[str, str | None] = Field(default_factory=dict, max_length=3)
    dependencies: dict[str, str] = Field(default_factory=dict, max_length=3)
    features: dict[str, float] = Field(max_length=len(FEATURES))


def read_plan(value: Any) -> ExitTimingPlan | None:
    try:
        plan = ExitTimingPlan.model_validate(value)
    except (ValueError, TypeError, ValidationError):
        return None
    if (
        plan.created_at.tzinfo is None
        or plan.selected_horizon_seconds not in HORIZONS
        or plan.selected_horizon_seconds > RISK_LIMITS[plan.risk_mode].max_hold_seconds
        or set(plan.features) != set(FEATURES)
    ):
        return None
    return plan


def is_contextual(artifact: ChallengerSkillArtifact) -> bool:
    # Either marker makes a damaged/partially changed contract fail closed.
    return artifact.recipe_version == RECIPE or artifact.implementation_version == IMPLEMENTATION


@dataclass(frozen=True)
class ContextPolicy:
    baseline: int
    # Ordered by horizon; immutable parsed parameters can safely be shared between reads.
    models: tuple[tuple[int, tuple[float, ...], tuple[float, ...], tuple[float, ...]], ...]

    def select(self, features: dict[str, float]) -> tuple[int, bool]:
        if any(
            isinstance(features.get(name), bool)
            or not isinstance(features.get(name), int | float)
            or not math.isfinite(features[name])
            for name in FEATURES
        ):
            return self.baseline, False
        predictions: dict[int, float] = {}
        for horizon, means, scales, coefficients in self.models:
            row = [
                (features[name] - mean) / scale
                for name, mean, scale in zip(FEATURES, means, scales, strict=True)
            ]
            if any(not math.isfinite(value) or abs(value) > SUPPORT_Z for value in row):
                return self.baseline, False
            value = coefficients[0] + sum(
                x * weight for x, weight in zip(row, coefficients[1:], strict=True)
            )
            if not math.isfinite(value):
                return self.baseline, False
            predictions[horizon] = max(-1.0, min(3.0, value))
        selected = max(predictions, key=lambda horizon: (predictions[horizon], horizon))
        if predictions[selected] < predictions[self.baseline] + MINIMUM_PREDICTED_EDGE:
            return self.baseline, True
        return selected, True


@lru_cache(maxsize=8)
def _decode(payload: str, baseline: int) -> ContextPolicy | None:
    try:
        data = json.loads(payload)
        horizons = tuple(h for h in HORIZONS if h <= baseline)
        if (
            set(data) != {"baseline_horizon_seconds", "models"}
            or type(data["baseline_horizon_seconds"]) is not int
            or data["baseline_horizon_seconds"] != baseline
            or not isinstance(data["models"], dict)
            or set(data["models"]) != {str(h) for h in horizons}
        ):
            return None
        models = []
        for horizon in horizons:
            parts = data["models"][str(horizon)]
            if not isinstance(parts, dict) or set(parts) != {"means", "scales", "coefficients"}:
                return None
            vectors = []
            for name, width in (
                ("means", len(FEATURES)),
                ("scales", len(FEATURES)),
                ("coefficients", len(FEATURES) + 1),
            ):
                vector = parts[name]
                if (
                    not isinstance(vector, list)
                    or len(vector) != width
                    or any(
                        isinstance(v, bool)
                        or not isinstance(v, int | float)
                        or not math.isfinite(v)
                        for v in vector
                    )
                ):
                    return None
                vectors.append(tuple(float(v) for v in vector))
            if any(scale < 0.01 for scale in vectors[1]):
                return None
            models.append((horizon, vectors[0], vectors[1], vectors[2]))
        return ContextPolicy(baseline, tuple(models))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def load_policy(artifact: ChallengerSkillArtifact) -> ContextPolicy | None:
    if (
        artifact.skill != ChallengerSkill.EXIT
        or artifact.schema_version != "challenger-skill-v2"
        or artifact.recipe_version != RECIPE
        or artifact.implementation_version != IMPLEMENTATION
        or artifact.model_family != "linear"
        or artifact.payload_format != "inline"
        or artifact.feature_names != list(FEATURES)
    ):
        return None
    try:
        payload = json.dumps(
            artifact.parameters, separators=(",", ":"), sort_keys=True, allow_nan=False
        )
    except (TypeError, ValueError):
        return None
    if (
        len(payload) > 24000
        or hashlib.sha256(payload.encode()).hexdigest() != artifact.payload_digest
    ):
        return None
    return _decode(payload, RISK_LIMITS[artifact.risk_mode].max_hold_seconds)
