from __future__ import annotations

import math
import sqlite3
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    LearningEngine,
    _challenger_cohort_key,
    _fit,
    _predict_named_parts,
    _rmse,
)
from signal_arcade.intelligence.nonlinear import (
    XGBOOST_IMPLEMENTATION_VERSION,
    XGBOOST_MINIMUM_TRAINING_SAMPLES,
    fit_xgboost,
    load_xgboost,
    predict_xgboost,
    xgboost_metadata,
    xgboost_payload_digest,
)
from signal_arcade.models import (
    ChallengerSkill,
    ChallengerSkillArtifact,
    RiskMode,
    StatisticalModelFamily,
)
from signal_arcade.strategy import BASELINE_VERSION

FEATURES = ("left", "right", "context")


def _rows(kind: str, count: int = 600) -> tuple[list[list[float]], list[float]]:
    rows: list[list[float]] = []
    outcomes: list[float] = []
    for index in range(count):
        left = ((index * 37) % 101) / 50 - 1
        right = ((index * 61 + 7) % 103) / 51 - 1
        context = ((index * 17 + 3) % 97) / 48 - 1
        noise = 0.01 * math.sin(index * 0.7)
        rows.append([left, right, context])
        if kind == "linear":
            outcomes.append(0.45 * left - 0.25 * right + 0.10 * context + noise)
        elif kind == "nonlinear":
            outcomes.append((0.28 if left * right > 0 else -0.22) + 0.06 * context + noise)
        else:
            outcomes.append(0.10 * math.sin(index * 1.917) + 0.02 * math.cos(index * 0.37))
    return rows, outcomes


def _linear_predictions(
    training_rows: list[list[float]],
    training_outcomes: list[float],
    validation_rows: list[list[float]],
) -> list[float]:
    wrapped = [
        (SimpleNamespace(features=dict(zip(FEATURES, row, strict=True))), outcome)
        for row, outcome in zip(training_rows, training_outcomes, strict=True)
    ]
    fitted = _fit(wrapped, feature_names=FEATURES)  # type: ignore[arg-type]
    assert fitted is not None
    return [
        _predict_named_parts(fitted, dict(zip(FEATURES, row, strict=True)), FEATURES)
        for row in validation_rows
    ]


def test_xgboost_recipe_is_deterministic_bounded_and_cpu_only() -> None:
    rows, outcomes = _rows("nonlinear")
    started = time.monotonic()
    first = fit_xgboost(rows[:400], outcomes[:400])
    second = fit_xgboost(rows[:400], outcomes[:400])
    assert first is not None and second is not None
    assert first == second
    assert len(first) < 8 * 1024**2
    assert time.monotonic() - started < 10
    metadata = xgboost_metadata()
    assert metadata["device"] == "cpu"
    assert metadata["implementation_version"] == XGBOOST_IMPLEMENTATION_VERSION
    assert xgboost_payload_digest(first) == xgboost_payload_digest(second)


def test_nonlinear_family_earns_complexity_only_on_nonlinear_fixture() -> None:
    for kind in ("linear", "nonlinear", "noise"):
        rows, outcomes = _rows(kind)
        training_rows, validation_rows = rows[:400], rows[400:]
        training_outcomes, validation_outcomes = outcomes[:400], outcomes[400:]
        linear = _linear_predictions(training_rows, training_outcomes, validation_rows)
        payload = fit_xgboost(training_rows, training_outcomes)
        assert payload is not None
        nonlinear = predict_xgboost(load_xgboost(payload), validation_rows)
        naive = [sum(training_outcomes) / len(training_outcomes)] * len(validation_outcomes)
        linear_rmse = _rmse(linear, validation_outcomes)
        nonlinear_rmse = _rmse(nonlinear, validation_outcomes)
        naive_rmse = _rmse(naive, validation_outcomes)
        if kind == "linear":
            assert linear_rmse <= nonlinear_rmse
        elif kind == "nonlinear":
            assert nonlinear_rmse <= linear_rmse * 0.75
        else:
            assert min(linear_rmse, nonlinear_rmse) >= naive_rmse * 0.98


def test_xgboost_fails_closed_on_small_or_invalid_evidence() -> None:
    rows, outcomes = _rows("nonlinear", XGBOOST_MINIMUM_TRAINING_SAMPLES - 1)
    assert fit_xgboost(rows, outcomes) is None
    rows.append([float("nan"), 0.0, 0.0])
    outcomes.append(0.0)
    assert fit_xgboost(rows, outcomes) is None
    with pytest.raises(ValueError, match="invalid XGBoost payload"):
        load_xgboost(b'{"not":"an-xgboost-model"}')


def test_xgboost_challenger_round_trip_and_corruption_fail_closed(settings) -> None:  # type: ignore[no-untyped-def]
    base_rows, outcomes = _rows("nonlinear", XGBOOST_MINIMUM_TRAINING_SAMPLES)
    width = len(FEATURE_NAMES)
    rows = [row + [0.0] * (width - len(row)) for row in base_rows]
    payload = fit_xgboost(rows, outcomes)
    assert payload is not None
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "xgb-config")
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        "xgb-config",
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    artifact = ChallengerSkillArtifact(
        version="xgb-round-trip",
        skill=ChallengerSkill.ENTRY,
        created_at=datetime.now(UTC),
        model_family=StatisticalModelFamily.XGBOOST,
        implementation_version=XGBOOST_IMPLEMENTATION_VERSION,
        recipe_version="test",
        payload_format="json",
        payload_digest=xgboost_payload_digest(payload),
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="xgb-config",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=list(FEATURE_NAMES),
        parameters={"means": [0.0] * width, "scales": [10.0] * width},
    )
    learner._register_skill_artifact(artifact, cohort_key, payload=payload)  # noqa: SLF001
    features = dict(zip(FEATURE_NAMES, rows[0], strict=True))
    assert learner._predict_artifact(artifact, features) is not None  # noqa: SLF001
    database.close()

    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "UPDATE statistical_model_artifacts SET payload=? WHERE version=?",
            (b"corrupt", artifact.version),
        )
    reopened = Database(settings.database_path)
    restarted = LearningEngine(
        reopened,
        settings,
        configuration_fingerprint=lambda: "xgb-config",
    )
    restored = restarted.skill_artifacts[artifact.version]
    assert restarted._predict_artifact(restored, features) is None  # noqa: SLF001
    reopened.close()

    # A matching digest proves storage integrity, not that the bytes are a valid model. Loading
    # arbitrary digest-valid JSON must still fail closed instead of escaping an XGBoost exception.
    malformed = b'{"not":"an-xgboost-model"}'
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "UPDATE statistical_model_artifacts SET payload=?,payload_digest=? WHERE version=?",
            (malformed, xgboost_payload_digest(malformed), artifact.version),
        )
    reopened = Database(settings.database_path)
    restarted = LearningEngine(
        reopened,
        settings,
        configuration_fingerprint=lambda: "xgb-config",
    )
    restored = restarted.skill_artifacts[artifact.version]
    assert restarted._predict_artifact(restored, features) is None  # noqa: SLF001
    reopened.close()
