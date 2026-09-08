from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.config import Settings
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import (
    FEATURE_SCHEMA_VERSION,
    MANIPULATION_FEATURE_NAMES,
    SIZING_FEATURE_NAMES,
    LearningEngine,
    _challenger_cohort_key,
)
from signal_arcade.models import (
    ChallengerSkill,
    ChallengerSkillArtifact,
    LearningCheckpoint,
    LearningEvidenceEpisode,
    RiskMode,
)
from signal_arcade.strategy import BASELINE_VERSION
from test_learning import (
    make_decision,
    make_state,
    policy_episode_for,
    qualified_model,
    resolve_forward_primary,
)


def native_champion(
    learner: LearningEngine,
    skill: ChallengerSkill,
    created_at: datetime,
    *,
    intercept: float | None = None,
) -> ChallengerSkillArtifact:
    """Independent qualification is a fixture; activation must earn real forward proof."""
    names = (
        SIZING_FEATURE_NAMES
        if skill == ChallengerSkill.SIZING
        else MANIPULATION_FEATURE_NAMES
        if skill == ChallengerSkill.MANIPULATION
        else ()
    )
    artifact = ChallengerSkillArtifact(
        version=f"progression-{skill.value}",
        skill=skill,
        created_at=created_at,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=learner.configuration_fingerprint(),
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=list(names),
        parameters=(
            {"selected_horizon_seconds": 300, "baseline_horizon_seconds": 600}
            if skill == ChallengerSkill.EXIT
            else {
                "means": [0.0] * len(names),
                "scales": [1.0] * len(names),
                "coefficients": [
                    intercept
                    if intercept is not None
                    else (0.5 if skill == ChallengerSkill.SIZING else -0.2),
                    *([0.0] * len(names)),
                ],
            }
        ),
        qualified=True,
    )
    cohort = _challenger_cohort_key(
        artifact.risk_mode,
        artifact.configuration_fingerprint,
        artifact.baseline_version,
        artifact.feature_schema_version,
    )
    assert cohort
    learner._register_skill_artifact(artifact, cohort)  # noqa: SLF001
    return artifact


def record_policy(learner: LearningEngine, mint: str, at: datetime) -> LearningEvidenceEpisode:
    decision = make_decision(at, mint).model_copy(
        update={
            "configuration_fingerprint": learner.configuration_fingerprint(),
            "model_version": BASELINE_VERSION,
        }
    )
    assert learner.register(decision, make_state(mint), live=True, evaluation_actionable=True)
    resolve_forward_primary(learner, mint, at + timedelta(seconds=300), -0.1)
    episode = policy_episode_for(learner, mint)
    episode.checkpoints["600"] = LearningCheckpoint(
        horizon_seconds=600, observed_at=at + timedelta(seconds=600), net_return=-0.3
    )
    for trial in episode.size_trials.values():
        assert trial.entry_cost_lamports
        for horizon, retained in ((300, 0.9), (600, 0.7)):
            trial.checkpoints[str(horizon)] = LearningCheckpoint(
                horizon_seconds=horizon,
                observed_at=at + timedelta(seconds=horizon),
                exit_value_lamports=int(trial.entry_cost_lamports * retained),
            )
    learner.database.save_learning_evidence_episode(episode)
    return episode


@pytest.fixture
def progression(settings: Settings):  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    database.set_setting("demo_mode", False)
    learner = LearningEngine(
        database, settings, configuration_fingerprint=lambda: "progression-context"
    )
    yield learner, database, settings
    database.close()


def activate_first(learner: LearningEngine, skill: ChallengerSkill) -> ChallengerSkillArtifact:
    at = datetime.now(UTC) - timedelta(hours=2)
    artifact = native_champion(learner, skill, at)
    for index in range(30):
        record_policy(learner, f"first-{index}", at + timedelta(minutes=10 + index))
    learner.set_participation(True)
    assert learner.active_skill_versions == {skill.value: artifact.version}
    return artifact


@pytest.mark.parametrize(
    ("upstream", "downstream"),
    [
        (ChallengerSkill.MANIPULATION, ChallengerSkill.SIZING),
        (ChallengerSkill.MANIPULATION, ChallengerSkill.EXIT),
        (ChallengerSkill.SIZING, ChallengerSkill.EXIT),
    ],
)
def test_new_upstream_champion_progresses_while_downstream_is_active(
    progression,
    upstream: ChallengerSkill,
    downstream: ChallengerSkill,  # type: ignore[no-untyped-def]
) -> None:
    learner, database, settings = progression
    first = activate_first(learner, downstream)
    next_champion = native_champion(learner, upstream, datetime.now(UTC))
    frozen_artifact = next_champion.model_dump()
    for index in range(30):
        record_policy(
            learner, f"next-{index}", next_champion.created_at + timedelta(minutes=1 + index)
        )
    proof = learner._skill_join_evidence(next_champion, independent=True)  # noqa: SLF001
    assert proof["ready"] and proof["usable_count"] == 30
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {upstream.value: next_champion.version}
    assert next_champion.model_dump() == frozen_artifact
    state = learner._current_skill_state(downstream)  # noqa: SLF001
    assert state and state.champion_version == first.version and state.active_version is None
    assert state.suspended_version is None
    assert state.last_tournament["result"] == "dependency_activated"
    # Existing standalone proof cannot authorize the changed downstream composition.
    assert not learner._skill_join_evidence(first, independent=True)["ready"]  # noqa: SLF001
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == learner.active_skill_versions
    assert restarted.auto_participation


def test_exit_rejoins_after_sizing_with_fresh_proof_and_fresh_health(progression) -> None:  # type: ignore[no-untyped-def]
    learner, database, settings = progression
    exit_champion = activate_first(learner, ChallengerSkill.EXIT)
    sizing = native_champion(learner, ChallengerSkill.SIZING, datetime.now(UTC))
    at = sizing.created_at + timedelta(minutes=1)
    for index in range(30):
        record_policy(learner, f"size-proof-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {"sizing": sizing.version}
    assert learner.recommended_hold_seconds(RiskMode.BALANCED) == 600
    for index in range(30):
        record_policy(learner, f"exit-rejoin-{index}", at + timedelta(minutes=2, seconds=index))
    learner._govern_skill_ensemble()  # noqa: SLF001
    expected = {"sizing": sizing.version, "exit": exit_champion.version}
    assert learner.active_skill_versions == expected
    assert learner.recommended_hold_seconds(RiskMode.BALANCED) == 300
    # Reusing the same Exit artifact must not mix its old standalone health into this reign.
    health = learner._skill_health(ChallengerSkill.EXIT, exit_champion.version)  # noqa: SLF001
    assert health["state"] == "collecting" and health["observed_count"] == 0
    for index in range(30):
        record_policy(learner, f"both-active-{index}", at + timedelta(minutes=4, seconds=index))
    health = learner._skill_health(ChallengerSkill.EXIT, exit_champion.version)  # noqa: SLF001
    assert health["state"] == "healthy" and health["usable_count"] == 30
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == expected
    assert restarted._skill_health(ChallengerSkill.EXIT, exit_champion.version) == health  # noqa: SLF001


@pytest.mark.parametrize("failure", ["old_reign", "wrong_dependency", "unknown_skill"])
def test_active_health_cannot_reuse_a_different_activation_context(
    progression,
    failure: str,  # type: ignore[no-untyped-def]
) -> None:
    learner, _, _ = progression
    artifact = activate_first(learner, ChallengerSkill.EXIT)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(30):
        episode = record_policy(learner, f"health-{index}", at + timedelta(seconds=index))
        if failure != "old_reign":
            episode.active_skill_versions[
                "manipulation" if failure == "wrong_dependency" else "unknown"
            ] = "other-version"
            # Even a well-shaped supporting receipt from another composition is not current proof.
            episode.challenger_evaluations["other-version"] = episode.challenger_evaluations[
                artifact.version
            ].model_copy(
                update={
                    "artifact_version": "other-version",
                    "skill": ChallengerSkill.MANIPULATION,
                    "proposed_action": "support",
                }
            )
    if failure == "old_reign":
        state = learner._current_skill_state(ChallengerSkill.EXIT)  # noqa: SLF001
        assert state
        state.joined_at = at + timedelta(minutes=1)
    health = learner._skill_health(ChallengerSkill.EXIT, artifact.version)  # noqa: SLF001
    assert health["state"] == "collecting" and health["observed_count"] == 0


@pytest.mark.parametrize(
    "failure",
    [
        "missing_bounds",
        "unsupported",
        "no_benefit",
        "missing_outcome",
        "pending",
        "wrong_upstream",
        "self_active",
        "unknown_skill",
        "late_receipt",
        "duplicate_mint",
        "wrong_cohort",
        "before_artifact",
        "coach_context",
        "harm_rate",
    ],
)
def test_downstream_tolerance_does_not_bypass_independent_safety_gates(
    progression,
    failure: str,  # type: ignore[no-untyped-def]
) -> None:
    learner, _, _ = progression
    exit_champion = activate_first(learner, ChallengerSkill.EXIT)
    sizing = native_champion(learner, ChallengerSkill.SIZING, datetime.now(UTC))
    at = sizing.created_at + timedelta(minutes=1)
    for index in range(30):
        episode = record_policy(learner, f"guard-{index}", at + timedelta(seconds=index))
        receipt = episode.challenger_evaluations[sizing.version]
        if failure == "missing_bounds":
            receipt.parameters.clear()
        elif failure == "unsupported":
            receipt.in_distribution = False
        elif failure == "no_benefit":
            receipt.parameters["bounded_multiplier"] = 1.0
        elif failure == "missing_outcome":
            episode.size_trials["0.5"].checkpoints["300"].exit_value_lamports = None
        elif failure == "pending":
            episode.checkpoints.pop("300")
        elif failure in {"wrong_upstream", "self_active", "unknown_skill"}:
            name = {"wrong_upstream": "entry", "self_active": "sizing"}.get(failure, "unknown")
            episode.active_skill_versions[name] = "other-version"
        elif failure == "late_receipt":
            receipt.evaluated_at = episode.created_at + timedelta(seconds=1)
        elif failure == "duplicate_mint":
            episode.mint = "same-token"
        elif failure == "wrong_cohort":
            episode.configuration_fingerprint = "different-context"
        elif failure == "harm_rate":
            baseline = episode.size_trials["1"]
            selected = episode.size_trials["0.5"]
            assert baseline.entry_cost_lamports and selected.entry_cost_lamports
            baseline_value = baseline.checkpoints["300"].exit_value_lamports
            assert baseline_value
            baseline_return = baseline_value / baseline.entry_cost_lamports - 1
            delta = -0.0001 if index < 12 else 0.1
            selected.checkpoints["300"].exit_value_lamports = int(
                selected.entry_cost_lamports
                + (baseline_return + delta) * baseline.entry_cost_lamports
            )
    if failure == "before_artifact":
        sizing.created_at = at + timedelta(minutes=1)
    elif failure == "coach_context":
        sizing.schema_version = "challenger-skill-coach-v1"
        sizing.dependency_versions = {"exit": exit_champion.version}
    proof = learner._skill_join_evidence(sizing, independent=True)  # noqa: SLF001
    assert not proof["ready"]
    if failure == "harm_rate":
        assert proof["uplift_lower_bound"] > 0 and proof["harm_fraction"] > 0.35
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {"exit": exit_champion.version}


@pytest.mark.parametrize(
    ("usable", "observed", "ready"),
    [(29, 30, False), (30, 30, True), (41, 60, False), (42, 60, True)],
)
def test_upstream_join_preserves_sample_and_coverage_boundaries(
    progression,
    usable: int,
    observed: int,
    ready: bool,  # type: ignore[no-untyped-def]
) -> None:
    learner, _, _ = progression
    activate_first(learner, ChallengerSkill.EXIT)
    sizing = native_champion(learner, ChallengerSkill.SIZING, datetime.now(UTC))
    for index in range(observed):
        episode = record_policy(
            learner, f"coverage-{index}", sizing.created_at + timedelta(minutes=1, seconds=index)
        )
        if index >= usable:
            episode.size_trials["0.5"].checkpoints["300"].exit_value_lamports = None
    proof = learner._skill_join_evidence(sizing, independent=True)  # noqa: SLF001
    assert proof["usable_count"] == usable and proof["observed_count"] == observed
    assert proof["ready"] == ready


@pytest.mark.parametrize("outcome", ["harmful", "unavailable", "pending"])
def test_active_composition_health_keeps_safe_upstream_and_preserves_permission(
    progression,
    outcome: str,  # type: ignore[no-untyped-def]
) -> None:
    learner, database, settings = progression
    sizing = activate_first(learner, ChallengerSkill.SIZING)
    exit_champion = native_champion(learner, ChallengerSkill.EXIT, datetime.now(UTC))
    at = exit_champion.created_at + timedelta(minutes=1)
    for index in range(30):
        record_policy(learner, f"exit-proof-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()  # noqa: SLF001
    both = {"sizing": sizing.version, "exit": exit_champion.version}
    assert learner.active_skill_versions == both
    for index in range(30):
        episode = record_policy(
            learner, f"health-now-{index}", at + timedelta(minutes=2, seconds=index)
        )
        trial = episode.size_trials["0.5"]
        assert trial.entry_cost_lamports
        if outcome == "harmful":
            # Sizing still saves on the 5m loss; waiting to Baseline's 10m review is better.
            trial.checkpoints["600"].exit_value_lamports = trial.entry_cost_lamports
        elif outcome == "unavailable":
            trial.checkpoints["600"].exit_value_lamports = None
        else:
            episode.checkpoints.pop("600")
        database.save_learning_evidence_episode(episode)
    learner._govern_skill_ensemble()  # noqa: SLF001
    expected = both if outcome == "pending" else {"sizing": sizing.version}
    assert learner.active_skill_versions == expected
    assert learner.auto_participation and database.get_setting("challenger_auto_participation")
    state = learner._current_skill_state(ChallengerSkill.EXIT)  # noqa: SLF001
    assert state
    if outcome != "pending":
        assert state.suspended_version == exit_champion.version
        assert state.suspension_reason == ("degraded" if outcome == "harmful" else "unverifiable")
        learner._govern_skill_ensemble()  # noqa: SLF001
        assert (
            learner.active_skill_versions == expected
        )  # no automatic retry of a suspended version
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == expected


@pytest.mark.parametrize("context", ["matching", "other_version", "before_dependency_join"])
def test_sizing_with_entry_and_exit_still_requires_exact_fresh_upstream_proof(
    progression,
    monkeypatch: pytest.MonkeyPatch,
    context: str,  # type: ignore[no-untyped-def]
) -> None:
    learner, _, _ = progression
    at = datetime.now(UTC)
    entry = qualified_model("progression-entry", 0.2, 80).model_copy(
        update={"created_at": at, "configuration_fingerprint": learner.configuration_fingerprint()}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        entry,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=at - timedelta(hours=1),
        evidence_ended_at=at,
    )
    monkeypatch.setattr(learner, "entry_outcome_availability", lambda: {"qualified": True})
    learner.set_participation(True)
    entry_version = learner.active_skill_versions["entry"]
    exit_champion = native_champion(learner, ChallengerSkill.EXIT, at)
    for index in range(30):
        record_policy(learner, f"entry-exit-{index}", at + timedelta(minutes=1, seconds=index))
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {"entry": entry_version, "exit": exit_champion.version}
    sizing = native_champion(learner, ChallengerSkill.SIZING, datetime.now(UTC))
    for index in range(30):
        episode = record_policy(
            learner, f"entry-size-{index}", at + timedelta(minutes=2, seconds=index)
        )
        if context == "other_version":
            episode.active_skill_versions["entry"] = "other-entry-generation"
            episode.challenger_evaluations["other-entry-generation"] = (
                episode.challenger_evaluations[entry_version].model_copy(
                    update={"artifact_version": "other-entry-generation"}
                )
            )
    if context == "before_dependency_join":
        state = learner._current_skill_state(ChallengerSkill.ENTRY)  # noqa: SLF001
        assert state
        state.joined_at = at + timedelta(minutes=3)
    proof = learner._skill_join_evidence(sizing, independent=True)  # noqa: SLF001
    assert proof["ready"] == (context == "matching")
    if context == "matching":
        learner._govern_skill_ensemble()  # noqa: SLF001
        assert learner.active_skill_versions == {"entry": entry_version, "sizing": sizing.version}
        health = learner._skill_health(ChallengerSkill.ENTRY, entry_version)  # noqa: SLF001
        assert health["state"] == "healthy" and health["usable_count"] == 60


@pytest.mark.parametrize("recent", ["beneficial", "harmful", "unavailable"])
def test_current_activation_health_uses_latest_resolved_window(
    progression,
    recent: str,  # type: ignore[no-untyped-def]
) -> None:
    learner, _, _ = progression
    sizing = activate_first(learner, ChallengerSkill.SIZING)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(120):
        episode = record_policy(learner, f"window-{index}", at + timedelta(seconds=index))
        trial = episode.size_trials["0.5"]
        assert trial.entry_cost_lamports
        outcome = recent if index >= 60 else "harmful" if recent == "beneficial" else "beneficial"
        if outcome == "harmful":
            trial.checkpoints["300"].exit_value_lamports = trial.entry_cost_lamports // 10
        elif outcome == "unavailable":
            trial.checkpoints["300"].exit_value_lamports = None
    # New entries still unfolding cannot displace the completed health window.
    for index in range(60):
        episode = record_policy(
            learner, f"pending-{index}", at + timedelta(minutes=3, seconds=index)
        )
        episode.checkpoints.pop("300")
    health = learner._skill_health(ChallengerSkill.SIZING, sizing.version)  # noqa: SLF001
    assert health["observed_count"] == 60
    assert health["usable_count"] == (0 if recent == "unavailable" else 60)
    assert (
        health["state"]
        == {
            "beneficial": "healthy",
            "harmful": "degraded",
            "unavailable": "unverifiable",
        }[recent]
    )
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == (
        {"sizing": sizing.version} if recent == "beneficial" else {}
    )
    assert learner.auto_participation


@pytest.mark.parametrize("invalid", ["missing", "nonfinite", "wrong_dependencies"])
def test_invalid_active_proof_cannot_report_healthy_or_keep_authority(
    progression,
    invalid: str,  # type: ignore[no-untyped-def]
) -> None:
    learner, database, settings = progression
    sizing = activate_first(learner, ChallengerSkill.SIZING)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(30):
        record_policy(learner, f"current-{index}", at + timedelta(seconds=index))
    assert learner._skill_health(ChallengerSkill.SIZING, sizing.version)["state"] == "healthy"  # noqa: SLF001
    state = learner._current_skill_state(ChallengerSkill.SIZING)  # noqa: SLF001
    assert state
    if invalid == "missing":
        state.activation_proof = {}
    elif invalid == "nonfinite":
        state.activation_proof["uplift_lower_bound"] = float("nan")
    else:
        state.activation_proof["dependencies"] = {"entry": "other-entry"}
    health = learner._skill_health(ChallengerSkill.SIZING, sizing.version)  # noqa: SLF001
    assert health["state"] == "suspended"
    assert health["suspension_reason"] == "activation_proof_unavailable"
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {}
    assert state.champion_version == sizing.version and state.suspended_version == sizing.version
    assert learner.auto_participation
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == {} and restarted.auto_participation
