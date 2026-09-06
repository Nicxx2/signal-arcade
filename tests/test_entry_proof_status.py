from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import (
    FEATURE_SCHEMA_VERSION,
    SKILL_ARTIFACT_VERSION_PREFIX,
    LearningEngine,
    _challenger_cohort_key,
    _entry_family_proof_gates,
    _entry_qualification_gates,
)
from signal_arcade.models import (
    ChallengerSkill,
    ChallengerSkillArtifact,
    ChallengerSkillState,
    RiskMode,
    StatisticalModelFamily,
)
from signal_arcade.strategy import BASELINE_VERSION
from test_learning import qualified_model


def artifact(version="entry-linear", family=StatisticalModelFamily.LINEAR):
    return ChallengerSkillArtifact(
        version=version,
        skill=ChallengerSkill.ENTRY,
        model_family=family,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="proof-context",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        metrics={
            "validation_rmse": 0.05,
            "naive_rmse": 0.2,
            "rank_fit": 0.5,
            "baseline_rank_fit": 0.1,
            "top_return": 0.2,
            "top_uplift": 0.1,
            "outcome_availability": 0.9,
            "in_distribution_fraction": 0.98,
            "policy_samples": 30,
            "policy_outcome_availability": 0.9,
            "policy_supported": 20,
            "policy_vetoes": 10,
            "policy_winner_veto_fraction": 0.1,
            "policy_uplift_lower": 0.02,
            "complexity_earned": True,
        },
        qualified=True,
    )


def globals_for(ready):
    return _entry_qualification_gates(
        None,
        usable_outcomes=120,
        current_availability={
            "availability_fraction": 0.8,
            "minimum_fraction": 0.7,
            "observed_count": 120,
        },
        activation_available=ready,
    )


def test_family_proof_is_saved_evidence_not_a_new_qualification_decision():
    linear = artifact()
    nonlinear = artifact("xgb", StatisticalModelFamily.XGBOOST)
    nonlinear.qualified = False
    nonlinear.metrics["complexity_earned"] = False
    before = nonlinear.model_dump_json()
    assert len(_entry_family_proof_gates(linear)) == 13
    gates = {g["id"]: g for g in _entry_family_proof_gates(nonlinear)}
    assert len(gates) == 14
    assert gates["entry_complexity_earned"]["state"] == "not_met"
    assert gates["entry_qualified"]["state"] == "not_met"
    assert nonlinear.model_dump_json() == before


@pytest.mark.parametrize("value", [None, float("inf"), float("nan"), True])
def test_missing_or_malformed_measurements_are_unknown(value):
    item = artifact()
    item.metrics.update(validation_rmse=value, naive_rmse=value, policy_uplift_lower=value)
    gates = {g["id"]: g for g in _entry_family_proof_gates(item)}
    assert gates["entry_validation_rmse"]["current"] is None
    assert gates["entry_validation_rmse"]["target"] is None
    assert gates["entry_validation_rmse"]["state"] == "collecting"
    assert gates["entry_policy_uplift_lower"]["current"] is None


def test_linear_familiarity_only_comes_from_its_exact_source():
    source = qualified_model("original", 0.2, 100)
    source.configuration_fingerprint = "proof-context"
    item = artifact(f"{SKILL_ARTIFACT_VERSION_PREFIX}entry-{source.version}")
    del item.metrics["in_distribution_fraction"]

    def current(src):
        return next(
            g
            for g in _entry_family_proof_gates(item, source=src)
            if g["id"] == "entry_in_distribution_fraction"
        )["current"]

    assert current(source) == 1
    assert current(source.model_copy(update={"version": "newest-unrelated"})) is None
    assert current(source.model_copy(update={"configuration_fingerprint": "other"})) is None
    assert current(None) is None
    assert "in_distribution_fraction" not in item.metrics


def test_status_separates_latest_families_from_the_older_eligible_champion(settings):
    db = Database(settings.database_path)
    learner = LearningEngine(db, settings, configuration_fingerprint=lambda: "proof-context")
    champion = artifact("champion-xgb", StatisticalModelFamily.XGBOOST)
    latest = champion.model_copy(
        update={
            "version": "latest-xgb",
            "qualified": False,
            "created_at": datetime.now(UTC) + timedelta(seconds=1),
        }
    )
    linear = artifact()
    linear.qualified = False
    unrelated = linear.model_copy(
        update={
            "version": "other-context",
            "configuration_fingerprint": "other",
            "created_at": latest.created_at + timedelta(days=1),
        }
    )
    learner.skill_artifacts = {a.version: a for a in [champion, latest, linear, unrelated]}
    cohort = _challenger_cohort_key(
        RiskMode.BALANCED, "proof-context", BASELINE_VERSION, FEATURE_SCHEMA_VERSION
    )
    assert cohort is not None
    state = ChallengerSkillState(
        cohort_key=cohort,
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="proof-context",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        champion_version=champion.version,
        latest_candidate_version=latest.version,
    )
    learner.skill_states[(cohort, ChallengerSkill.ENTRY)] = state
    original = state.model_dump_json()
    changes = db._conn.total_changes
    proof = learner.entry_proof_status(
        globals_for(True), activation_candidate=None, skill_activation_candidate=champion
    )
    assert [f["artifact"]["version"] for f in proof["families"]] == [linear.version, latest.version]
    assert proof["activation"]["subject"]["version"] == champion.version
    assert proof["activation"]["ready"] is True
    assert proof["activation"]["source"] == "skill_champion"
    assert proof["activation"]["gates"][-1]["current"] is True
    assert state.model_dump_json() == original
    assert db._conn.total_changes == changes
    state.suspended_version = champion.version
    blocked = learner.entry_proof_status(
        globals_for(False), activation_candidate=None, skill_activation_candidate=None
    )
    assert blocked["activation"]["ready"] is False
    assert blocked["activation"]["champion"]["version"] == champion.version
    db.close()


def test_empty_and_legacy_status_do_not_invent_a_champion(settings):
    db = Database(settings.database_path)
    learner = LearningEngine(db, settings, configuration_fingerprint=lambda: "proof-context")
    legacy = qualified_model("legacy", 0.2, 100)
    proof = learner.entry_proof_status(
        globals_for(True), activation_candidate=legacy, skill_activation_candidate=None
    )
    assert all(f["artifact"] is None and f["gates"] == [] for f in proof["families"])
    assert proof["activation"]["champion"] is None
    assert proof["activation"]["source"] == "legacy_linear"
    assert proof["activation"]["ready"] is True
    assert learner.status(demo_mode=False)["entry_proof"]["version"] == "entry-proof-v1"
    db.close()
