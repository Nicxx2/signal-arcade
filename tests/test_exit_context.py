"""Contextual timing must be fixed before outcomes and stay within Baseline boundaries."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.exit_context import (
    FEATURES,
    HORIZONS,
    IMPLEMENTATION,
    RECIPE,
    ExitTimingPlan,
    load_policy,
    read_plan,
)
from signal_arcade.intelligence.learning import FEATURE_SCHEMA_VERSION, _stable_digest
from signal_arcade.models import RISK_LIMITS, ChallengerSkill, ChallengerSkillArtifact, RiskMode
from signal_arcade.paper.broker import PaperBroker
from signal_arcade.strategy import BASELINE_VERSION
from test_broker import make_broker, make_decision, make_features
from test_learning import make_state


def contextual_artifact(mode=RiskMode.BALANCED, *, version="contextual-exit", created_at=None):
    baseline = RISK_LIMITS[mode].max_hold_seconds
    models = {}
    for horizon in HORIZONS:
        if horizon > baseline:
            continue
        coefficients = [0.0] * (len(FEATURES) + 1)
        if horizon < baseline:
            coefficients[0] = 0.0 if horizon == 60 else 0.6
            coefficients[1] = 1.0 if horizon == 60 else -1.0
        models[str(horizon)] = {
            "means": [0.0] * len(FEATURES),
            "scales": [1.0] * len(FEATURES),
            "coefficients": coefficients,
        }
    parameters = {"baseline_horizon_seconds": baseline, "models": models}
    return ChallengerSkillArtifact(
        version=version,
        created_at=created_at or datetime.now(UTC),
        skill=ChallengerSkill.EXIT,
        schema_version="challenger-skill-v2",
        implementation_version=IMPLEMENTATION,
        recipe_version=RECIPE,
        risk_mode=mode,
        configuration_fingerprint="progression-context",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=list(FEATURES),
        parameters=parameters,
        payload_digest=_stable_digest(parameters),
        qualified=True,
    )


def entry_features(opportunity=0.8):
    return {name: opportunity if name == "opportunity" else 0.0 for name in FEATURES}


@pytest.mark.parametrize("mode", list(RiskMode))
def test_contextual_selection_is_per_entry_and_bounded(mode):
    policy = load_policy(contextual_artifact(mode))
    assert policy
    assert policy.select(entry_features(0.9)) == (60, True)
    selected, supported = policy.select(entry_features(0.1))
    assert supported and selected <= RISK_LIMITS[mode].max_hold_seconds
    assert selected == {RiskMode.SAFE: 60, RiskMode.BALANCED: 300, RiskMode.AGGRESSIVE: 900}[mode]


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf"), 100])
def test_missing_or_unfamiliar_context_keeps_baseline(value):
    policy = load_policy(contextual_artifact())
    features = entry_features()
    if value is None:
        features.pop("momentum")
    else:
        features["momentum"] = value
    assert policy.select(features) == (600, False)


@pytest.mark.parametrize(
    "damage", ["digest", "shape", "nan", "scale", "horizon", "recipe", "family"]
)
def test_corrupt_contract_cannot_be_used_even_with_familiar_features(damage):
    artifact = contextual_artifact()
    if damage == "digest":
        artifact.payload_digest = "0" * 64
    elif damage == "shape":
        artifact.parameters["models"]["60"]["coefficients"].pop()
    elif damage == "nan":
        artifact.parameters["models"]["60"]["means"][0] = float("nan")
    elif damage == "scale":
        artifact.parameters["models"]["60"]["scales"][0] = 0
    elif damage == "horizon":
        artifact.parameters["models"]["1800"] = artifact.parameters["models"]["60"]
    elif damage == "recipe":
        artifact.recipe_version = "other"
    else:
        artifact.model_family = "deterministic"
    if damage != "digest":
        artifact.payload_digest = _stable_digest(artifact.parameters)
    assert load_policy(artifact) is None


def test_tie_and_tiny_predicted_edge_keep_normal_review():
    artifact = contextual_artifact()
    for model in artifact.parameters["models"].values():
        model["coefficients"] = [0.0] * (len(FEATURES) + 1)
    artifact.parameters["models"]["60"]["coefficients"][0] = 0.009
    artifact.payload_digest = _stable_digest(artifact.parameters)
    assert load_policy(artifact).select(entry_features()) == (600, True)


def test_plan_round_trip_and_malformed_optional_record():
    artifact = contextual_artifact()
    plan = ExitTimingPlan(
        decision_id="decision",
        artifact_version=artifact.version,
        payload_digest=artifact.payload_digest,
        selected_horizon_seconds=60,
        created_at=datetime.now(UTC),
        risk_mode=artifact.risk_mode,
        configuration_fingerprint=artifact.configuration_fingerprint,
        baseline_version=artifact.baseline_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        joined_at=datetime.now(UTC).isoformat(),
        features=entry_features(),
    )
    encoded = plan.model_dump(mode="json")
    assert read_plan(encoded) == plan
    assert read_plan(None) is None
    for patch in (
        {"selected_horizon_seconds": True},
        {"selected_horizon_seconds": 900},
        {"created_at": "2026-09-08"},
        {"features": {}},
        {"payload_digest": "bad"},
    ):
        assert read_plan({**encoded, **patch}) is None


def test_timing_receipt_survives_order_latency_fill_and_restart(settings):
    settings.entry_latency_ms = 1000
    database = Database(settings.database_path)
    try:
        broker = make_broker(database, settings)
        at = datetime.now(UTC)
        retained = {
            "schema_version": "entry-exit-plan-v1",
            "selected_horizon_seconds": 60,
            "features": entry_features(),
        }
        order, blocker = broker.submit_decision_with_reason(
            make_decision(at), exit_timing_plan=retained
        )
        assert order and blocker is None
        retained["features"]["opportunity"] = 0.0
        assert order.exit_timing_plan["features"]["opportunity"] == 0.8
        restarted = PaperBroker(database, settings)
        pending = restarted.pending[order.order_id]
        assert pending.exit_timing_plan == order.exit_timing_plan
        state = make_state("mint")
        filled_at = at + timedelta(seconds=2)
        state.last_event_at = state.last_reserve_at = filled_at
        assert restarted.process_due_orders(
            state=state,
            features=make_features(filled_at),
            source_event_id="fill",
            now=filled_at,
            mode=RiskMode.BALANCED,
        )
        position = restarted.positions["mint"]
        assert position.opened_at == filled_at
        assert position.exit_timing_plan == order.exit_timing_plan
        assert (
            PaperBroker(database, settings).positions["mint"].exit_timing_plan
            == order.exit_timing_plan
        )
    finally:
        database.close()
