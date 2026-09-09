"""A contextual crown still needs forward proof, permissions and an unchanged composition."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from signal_arcade.intelligence.learning import (
    LearningEngine,
    _challenger_cohort_key,
    _participation_values,
    _size_trial_value,
)
from signal_arcade.models import (
    ChallengerEvaluationReceipt,
    ChallengerSkill,
    CoachExperimentKind,
    LearningCheckpoint,
    LearningMode,
    Position,
    RiskMode,
)
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.strategy import BASELINE_VERSION
from test_exit_context import contextual_artifact
from test_learning import _supported_coach_hypothesis, make_decision
from test_participation_progression import progression, record_policy  # noqa: F401


def register_context(learner, version="contextual-exit", at=None):
    artifact = contextual_artifact(
        version=version, created_at=at or datetime.now(UTC) - timedelta(hours=2)
    )
    key = _challenger_cohort_key(
        artifact.risk_mode,
        artifact.configuration_fingerprint,
        artifact.baseline_version,
        artifact.feature_schema_version,
    )
    learner._register_skill_artifact(artifact, key)
    return artifact


def context_policy(learner, mint, at, outcome=0.1):
    row = record_policy(learner, mint, at)
    row.checkpoints["60"] = LearningCheckpoint(
        horizon_seconds=60, observed_at=at + timedelta(seconds=60), net_return=outcome
    )
    learner.database.save_learning_evidence_episode(row)
    return row


def activate_context(learner):
    artifact = register_context(learner)
    for index in range(30):
        context_policy(
            learner, f"proof-{index}", artifact.created_at + timedelta(minutes=1 + index)
        )
    learner.set_participation(True)
    assert learner.active_skill_versions == {"exit": artifact.version}
    return artifact


def position_with_plan(learner):
    at = datetime.now(UTC) + timedelta(seconds=1)
    decision = make_decision(at, "held").model_copy(
        update={"configuration_fingerprint": learner.configuration_fingerprint()}
    )
    plan = learner.freeze_exit_timing_plan(decision)
    assert plan and plan["selected_horizon_seconds"] == 60
    return Position(
        position_id="held",
        mint="held",
        symbol="HELD",
        token_units=100,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=at + timedelta(seconds=2),
        entry_fill_id="fill",
        risk_mode_at_entry=RiskMode.BALANCED,
        baseline_version_at_entry=BASELINE_VERSION,
        exit_timing_plan=plan,
    )


def test_forward_proof_and_position_plan_survive_restart(progression):  # noqa: F811
    learner, database, settings = progression
    artifact = activate_context(learner)
    position = position_with_plan(learner)
    assert learner.recommended_hold_seconds(RiskMode.BALANCED, position) == 60
    assert learner.recommended_hold_seconds(RiskMode.BALANCED) == 600
    assert (
        learner.exit_timing_participant(RiskMode.BALANCED, 60, position)["version"]
        == artifact.version
    )
    database.save_position(position)
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == learner.active_skill_versions
    state = restarted._current_skill_state(ChallengerSkill.EXIT)
    assert state.activation_proof["policy"] == "independent-exit-context-v2"
    # v1.10.8 recognises only independent-v1 for native skills: rollback rejects this authority.
    assert state.activation_proof["policy"] != "independent-v1"
    assert restarted.recommended_hold_seconds(RiskMode.BALANCED, position) == 60
    assert (
        restarted.recommended_hold_seconds(
            RiskMode.BALANCED, position.model_copy(update={"exit_timing_plan": None})
        )
        == 600
    )


@pytest.mark.parametrize(
    "change",
    [
        "off",
        "consent",
        "suspended",
        "digest",
        "risk",
        "configuration",
        "epoch",
        "dependencies",
        "plan",
        "authority",
    ],
)
def test_entry_plan_never_preserves_revoked_or_changed_authority(progression, change):  # noqa: F811
    learner, _, _ = progression
    artifact = activate_context(learner)
    position = position_with_plan(learner)
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    if change == "off":
        learner.set_mode(LearningMode.OFF)
    elif change == "consent":
        learner.consent_granted = False
    elif change == "suspended":
        learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    elif change == "digest":
        artifact.payload_digest = "0" * 64
    elif change == "risk":
        position.risk_mode_at_entry = RiskMode.SAFE
    elif change == "configuration":
        position.exit_timing_plan["configuration_fingerprint"] = "other"
    elif change == "epoch":
        state.joined_at += timedelta(seconds=1)
    elif change == "dependencies":
        learner.active_skill_versions["sizing"] = "another"
    elif change == "plan":
        position.exit_timing_plan = {"selected_horizon_seconds": 60}
    else:
        state.activation_proof = {}
    assert learner.recommended_hold_seconds(RiskMode.BALANCED, position) == 600
    assert learner.exit_timing_participant(RiskMode.BALANCED, 600, position) is None
    assert learner.exit_timing_selection(RiskMode.BALANCED, position) == (600, None)


def test_one_review_validates_exit_authority_once_and_rechecks_next_review(
    progression,  # noqa: F811
    monkeypatch,
):
    learner, _, _ = progression
    artifact = activate_context(learner)
    position = position_with_plan(learner)
    engine = SimpleNamespace(
        learning=learner,
        risk_mode=RiskMode.BALANCED,
        broker=SimpleNamespace(positions={position.mint: position}),
    )
    calls = []
    check = learner._active_exit_artifact

    def authority(mode):
        calls.append(mode)
        return check(mode)

    monkeypatch.setattr(learner, "_active_exit_artifact", authority)
    assert Orchestrator._exit_timing_arguments(engine, position.mint) == {
        "soft_hold_seconds": 60,
        "soft_hold_participant": {"kind": "champion", "skill": "exit", "version": artifact.version},
    }
    assert len(calls) == 1
    learner.consent_granted = False
    assert Orchestrator._exit_timing_arguments(engine, position.mint) == {
        "soft_hold_seconds": 600,
        "soft_hold_participant": None,
    }
    assert len(calls) == 2


def test_contextual_champion_can_recover_on_one_fixed_window(progression):  # noqa: F811
    learner, _, _ = progression
    artifact = activate_context(learner)
    old_position = position_with_plan(learner)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(59):
        context_policy(learner, f"recover-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    context_policy(learner, "recover-last", at + timedelta(seconds=60))
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {"exit": artifact.version}
    assert learner.recommended_hold_seconds(RiskMode.BALANCED, old_position) == 600


def test_active_contextual_health_counts_missing_receipts_as_unavailable(progression):  # noqa: F811
    learner, _, _ = progression
    artifact = activate_context(learner)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(30):
        row = context_policy(learner, f"missing-{index}", at + timedelta(seconds=index))
        row.challenger_evaluations.pop(artifact.version)
    health = learner._skill_health(ChallengerSkill.EXIT, artifact.version)
    assert health["observed_count"] == 30 and health["usable_count"] == 0
    assert health["state"] == "unverifiable"


def test_no_forward_proof_is_borrowed_from_a_waiting_contextual_candidate(progression):  # noqa: F811
    learner, _, _ = progression
    register_context(learner)
    register_context(learner, "testing")
    queued = register_context(learner, "queued")
    row = context_policy(learner, "forward", datetime.now(UTC) + timedelta(minutes=1))
    assert set(row.challenger_evaluations) == {"contextual-exit", "testing"}
    assert queued.version not in row.challenger_evaluations


@pytest.mark.parametrize("mask", range(8))
def test_exit_proof_respects_every_upstream_combination(progression, mask):  # noqa: F811
    learner, _, _ = progression
    artifact = register_context(learner)
    skills = [ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION, ChallengerSkill.SIZING]
    learner.active_skill_versions = {
        skill.value: f"upstream-{skill}" for i, skill in enumerate(skills) if mask & (1 << i)
    }
    at = datetime.now(UTC)
    for index in range(30):
        row = context_policy(learner, f"combination-{index}", at + timedelta(seconds=index))
        for name, version in learner.active_skill_versions.items():
            row.challenger_evaluations[version] = ChallengerEvaluationReceipt(
                artifact_version=version,
                skill=ChallengerSkill(name),
                evaluated_at=row.created_at,
                in_distribution=True,
                baseline_actionable=True,
                proposed_action="0.5" if name == "sizing" else "support",
                parameters={"bounds_policy": "sizing-authority-v1", "bounded_multiplier": 0.5}
                if name == "sizing"
                else {},
            )
        for trial in row.size_trials.values():
            trial.checkpoints["60"] = LearningCheckpoint(
                horizon_seconds=60,
                observed_at=row.created_at + timedelta(seconds=60),
                exit_value_lamports=int(trial.entry_cost_lamports * 1.1),
            )
    proof = learner._skill_join_evidence(artifact, independent=True)
    assert proof["ready"] and proof["usable_count"] == 30
    if "entry" in learner.active_skill_versions:
        for row in learner.evidence_episodes.values():
            row.challenger_evaluations["upstream-entry"].proposed_action = "veto"
        assert not learner._skill_join_evidence(artifact, independent=True)["ready"]


def test_unfamiliar_exit_context_preserves_the_actual_sizing_comparison(progression):  # noqa: F811
    learner, _, _ = progression
    artifact = register_context(learner)
    learner.active_skill_versions = {"sizing": "sized"}
    row = context_policy(learner, "unfamiliar", datetime.now(UTC))
    exit_receipt = row.challenger_evaluations[artifact.version]
    exit_receipt.in_distribution = False
    exit_receipt.proposed_action = "600"
    row.challenger_evaluations["sized"] = ChallengerEvaluationReceipt(
        artifact_version="sized",
        skill=ChallengerSkill.SIZING,
        evaluated_at=row.created_at,
        in_distribution=True,
        baseline_actionable=True,
        proposed_action="0.5",
        parameters={"bounds_policy": "sizing-authority-v1", "bounded_multiplier": 0.5},
    )
    expected = _size_trial_value(row, 0.5, horizon=600)
    assert _participation_values(row, exit_receipt) == (expected, expected)
    row.size_trials["0.5"].checkpoints.pop("600")
    assert _participation_values(row, exit_receipt) == (None, None)


def test_coach_fixed_exit_can_enter_a_battle_against_contextual_champion(progression):  # noqa: F811
    learner, _, _ = progression
    artifact = activate_context(learner)
    hypothesis = _supported_coach_hypothesis(datetime.now(UTC))
    hypothesis.kind = CoachExperimentKind.EARLIER_REVIEW
    hypothesis.skill = ChallengerSkill.EXIT
    hypothesis.hold_seconds = 300
    hypothesis.baseline_hold_seconds = 600
    hypothesis.conditions = []
    hypothesis.configuration_fingerprint = learner.configuration_fingerprint()
    hypothesis.dependency_versions = dict(learner.active_skill_versions)
    version, status = learner.seed_coach_candidate(hypothesis)
    assert version and status == "handed_off"
    assert learner._current_skill_state(ChallengerSkill.EXIT).testing_version == version
    assert learner.active_skill_versions == {"exit": artifact.version}
    row = context_policy(learner, "coach-battle", datetime.now(UTC) + timedelta(minutes=1))
    assert {artifact.version, version} <= row.challenger_evaluations.keys()


@pytest.mark.parametrize("value", [None, "invalid", [], 42, {"selected_horizon_seconds": "bad"}])
def test_bad_optional_plan_cannot_hide_an_existing_position(value):
    position = Position.model_validate(
        {
            "position_id": "held",
            "mint": "held",
            "symbol": "HELD",
            "token_units": 100,
            "entry_cost_lamports": 100,
            "book_value_lamports": 100,
            "opened_at": datetime.now(UTC).isoformat(),
            "entry_fill_id": "fill",
            "exit_timing_plan": value,
        }
    )
    assert position.token_units == 100


def test_held_position_reviews_do_not_run_model_inference_again(progression, monkeypatch):  # noqa: F811
    from signal_arcade.intelligence.exit_context import ContextPolicy

    learner, _, _ = progression
    activate_context(learner)
    position = position_with_plan(learner)

    def unexpected(*args):
        raise AssertionError("a held-position update must use its frozen choice")

    monkeypatch.setattr(ContextPolicy, "select", unexpected)
    for _ in range(100):
        assert learner.recommended_hold_seconds(RiskMode.BALANCED, position) == 60


def test_contextual_replacement_earns_a_battle_then_fresh_activation(progression):  # noqa: F811
    from test_participation_progression import activate_first

    learner, database, _ = progression
    previous = activate_first(learner, ChallengerSkill.EXIT)
    artifact = register_context(learner, at=datetime.now(UTC))
    at = artifact.created_at + timedelta(seconds=1)
    for index in range(30):
        context_policy(learner, f"battle-{index}", at + timedelta(seconds=index))
    learner._advance_entry_tournaments()
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    assert state.champion_version == artifact.version != previous.version
    assert database.champion_record(state)["champion_generation"] == 2
    assert "exit" not in learner.active_skill_versions
    learner._govern_skill_ensemble()
    assert "exit" not in learner.active_skill_versions
    for index in range(30):
        context_policy(learner, f"new-join-{index}", at + timedelta(minutes=2, seconds=index))
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {"exit": artifact.version}


def test_replacement_of_suspended_exit_cannot_reuse_its_battle_for_activation(progression):  # noqa: F811
    from test_participation_progression import activate_first

    learner, database, settings = progression
    activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    artifact = register_context(learner, at=datetime.now(UTC))
    at = artifact.created_at + timedelta(seconds=1)
    for index in range(30):
        context_policy(learner, f"suspended-battle-{index}", at + timedelta(seconds=index))
    learner._advance_entry_tournaments()
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    assert state.champion_version == artifact.version
    assert all(
        row.challenger_evaluations[artifact.version].parameters["champion_version_at_evaluation"]
        != artifact.version
        for row in learner.evidence_episodes.values()
        if artifact.version in row.challenger_evaluations
    )
    proof = learner._skill_join_evidence(artifact, independent=True)
    assert not proof["ready"]
    assert proof["observed_count"] == 0
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    learner = LearningEngine(
        database, settings, configuration_fingerprint=lambda: "progression-context"
    )
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    for index in range(30):
        context_policy(learner, f"fresh-join-{index}", at + timedelta(minutes=2, seconds=index))
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {"exit": artifact.version}


@pytest.mark.parametrize("previous_policy", ["independent-exit-context-v1", "independent-v1"])
def test_restart_rejects_contextual_authority_without_the_new_separation_contract(
    progression,  # noqa: F811
    previous_policy,
):
    learner, database, settings = progression
    artifact = activate_context(learner)
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    state.activation_proof["policy"] = previous_policy
    database.save_challenger_skill_state(state)
    # Early v1.10.9 review builds did not save a contender/Champion phase on receipts.
    for row in learner.evidence_episodes.values():
        receipt = row.challenger_evaluations.get(artifact.version)
        if receipt:
            receipt.parameters.pop("champion_version_at_evaluation", None)
            database.save_learning_evidence_episode(row)
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=lambda: "progression-context"
    )
    restarted._govern_skill_ensemble()
    assert not restarted.active_skill_versions
    assert restarted._current_skill_state(ChallengerSkill.EXIT).champion_version == artifact.version


@pytest.mark.parametrize(("unavailable", "ready"), [(18, True), (19, False)])
def test_post_crown_unknown_outcomes_still_reduce_activation_coverage(
    progression,  # noqa: F811
    unavailable,
    ready,
):
    learner, _, _ = progression
    artifact = register_context(learner)
    at = datetime.now(UTC)
    for index in range(60):
        row = context_policy(
            learner,
            f"post-crown-{index}",
            at + timedelta(seconds=index),
            outcome=None if index < unavailable else 0.1,
        )
        assert (
            row.challenger_evaluations[artifact.version].parameters[
                "champion_version_at_evaluation"
            ]
            == artifact.version
        )
    proof = learner._skill_join_evidence(artifact, independent=True)
    assert proof["observed_count"] == 60
    assert proof["usable_count"] == 60 - unavailable
    assert proof["availability_fraction"] == (60 - unavailable) / 60
    assert proof["ready"] is ready
