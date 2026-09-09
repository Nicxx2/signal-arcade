"""Suspension removes authority, but a fixed prospective trial may earn it back."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import ChallengerSkill, LearningMode
from signal_arcade.strategy import BASELINE_VERSION
from test_coach_lifecycle import coach_lifecycle, crowned_coach  # noqa: F401
from test_coach_lifecycle import record_policy as coach_policy
from test_learning import qualified_model
from test_participation_progression import activate_first, progression, record_policy  # noqa: F401


@pytest.mark.parametrize("skill", [ChallengerSkill.SIZING, ChallengerSkill.EXIT])
def test_suspended_champion_requires_complete_fresh_window_and_keeps_its_crown(
    progression,  # noqa: F811
    skill,
):
    learner, database, settings = progression
    artifact = activate_first(learner, skill)
    frozen = artifact.model_dump()
    state = learner._current_skill_state(skill)
    generation = database.champion_record(state)["champion_generation"]
    learner._suspend_skill(skill, "degraded")
    suspended_at = state.suspended_at
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(59):
        record_policy(learner, f"recover-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions  # no peeking at a promising prefix
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted._current_skill_state(skill).suspended_at == suspended_at
    record_policy(restarted, "recover-last", at + timedelta(seconds=60))
    restarted._govern_skill_ensemble()
    assert restarted.active_skill_versions == {skill.value: artifact.version}
    state = restarted._current_skill_state(skill)
    assert state.suspended_version is None
    assert state.activation_proof["recovery"]["status"] == "restored"
    assert state.activation_proof["recovery"]["suspended_at"] == suspended_at.isoformat()
    assert database.champion_record(state)["champion_generation"] == generation
    assert restarted.skill_artifacts[artifact.version].model_dump() == frozen
    again = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert again.active_skill_versions == restarted.active_skill_versions


def test_failed_recovery_does_not_slide_to_later_better_markets(progression):  # noqa: F811
    learner, _, _ = progression
    artifact = activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "unverifiable")
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(60):
        episode = record_policy(learner, f"missing-{index}", at + timedelta(seconds=index))
        episode.challenger_evaluations.pop(artifact.version)
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    for index in range(80):
        record_policy(learner, f"later-good-{index}", at + timedelta(minutes=2, seconds=index))
    learner._govern_skill_ensemble()
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    assert not learner.active_skill_versions
    assert state.activation_proof["recovery"]["status"] == "failed"
    assert state.activation_proof["recovery"]["observed_count"] == 60
    assert state.activation_proof["recovery"]["usable_count"] == 0
    assert learner.skill_suspension_summary(state)["failed_checks"] == [
        "usable_outcomes",
        "coverage",
        "advantage",
        "harm",
    ]


@pytest.mark.parametrize("skill", list(ChallengerSkill))
def test_coach_crown_can_recover_without_new_permission_or_new_crown(
    coach_lifecycle,  # noqa: F811
    skill,
):
    learner, database, settings = coach_lifecycle
    version = crowned_coach(learner, skill)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(81):
        coach_policy(learner, f"coach-join-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {skill.value: version}
    learner._suspend_skill(skill, "degraded")
    for index in range(60):
        coach_policy(learner, f"coach-recover-{index}", at + timedelta(minutes=3, seconds=index))
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {skill.value: version}
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == learner.active_skill_versions


@pytest.mark.parametrize(
    "reason",
    [
        "activation_proof_unavailable",
        "tournament_artifact_unavailable",
        "exit_comparison_proof_requires_requalification",
        None,
    ],
)
def test_structural_or_unknown_suspension_cannot_recover(progression, reason):  # noqa: F811
    learner, _, _ = progression
    activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, reason)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(65):
        record_policy(learner, f"blocked-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    assert "recovery" not in learner._current_skill_state(ChallengerSkill.EXIT).activation_proof


@pytest.mark.parametrize(
    "guard",
    [
        "off",
        "no_permission",
        "demo",
        "missing_artifact",
        "unqualified",
        "context",
        "corrupt",
        "disabled_legacy",
    ],
)
def test_complete_window_never_bypasses_guards(progression, guard):  # noqa: F811
    learner, database, _ = progression
    artifact = activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(60):
        record_policy(learner, f"guard-{index}", at + timedelta(seconds=index))
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    if guard == "off":
        learner.set_mode(LearningMode.OFF)
    elif guard == "no_permission":
        learner.set_participation(False)
    elif guard == "demo":
        database.set_setting("demo_mode", True)
    elif guard == "missing_artifact":
        learner.skill_artifacts.pop(artifact.version)
    elif guard == "unqualified":
        learner.skill_artifacts[artifact.version] = artifact.model_copy(update={"qualified": False})
    elif guard == "context":
        state.activation_proof["recovery"]["dependencies"] = {"sizing": "other"}
    elif guard == "corrupt":
        state.activation_proof["recovery"]["rows"][0]["deadline"] = "bad-date"
    else:
        learner.disabled_model_versions.add(artifact.version)
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions


def test_failed_authority_commit_keeps_memory_and_database_suspended(progression, monkeypatch):  # noqa: F811
    learner, database, settings = progression
    activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(60):
        record_policy(learner, f"commit-{index}", at + timedelta(seconds=index))
    original = database._upsert_settings

    def fail_authority(rows, now):
        if any(key == "active_challenger_skills" for key, _ in rows):
            raise RuntimeError("isolated authority commit failure")
        return original(rows, now)

    with monkeypatch.context() as scoped:
        scoped.setattr(database, "_upsert_settings", fail_authority)
        with pytest.raises(RuntimeError, match="authority commit"):
            learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert not restarted.active_skill_versions
    assert restarted._current_skill_state(ChallengerSkill.EXIT).suspended_version
    restarted._govern_skill_ensemble()
    assert restarted.active_skill_versions == {"exit": "progression-exit"}


@pytest.mark.parametrize(("usable", "ready"), [(41, False), (42, True), (60, True)])
def test_recovery_coverage_counts_every_preselected_row(progression, usable, ready):  # noqa: F811
    learner, _, _ = progression
    artifact = activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "unverifiable")
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(60):
        episode = record_policy(learner, f"coverage-{index}", at + timedelta(seconds=index))
        if index >= usable:
            episode.challenger_evaluations.pop(artifact.version)
    learner._govern_skill_ensemble()
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    recovery = state.activation_proof["recovery"]
    assert recovery["observed_count"] == 60 and recovery["usable_count"] == usable
    assert recovery["availability_fraction"] == usable / 60
    assert bool(learner.active_skill_versions) == ready


def test_pending_and_pruned_rows_are_not_replaced_or_silently_excluded(progression):  # noqa: F811
    learner, _, _ = progression
    activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    at = datetime.now(UTC) + timedelta(minutes=1)
    first = None
    for index in range(60):
        episode = record_policy(learner, f"pending-{index}", at + timedelta(seconds=index))
        if index == 0:
            first = episode
    saved = first.checkpoints.pop("600")
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    first.checkpoints["600"] = saved
    # A vanished row counts as unavailable only after its original deadline.
    # No new sample takes its place.
    learner.evidence_episodes.pop(first.episode_id)
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    learner._govern_skill_ensemble()
    assert state.activation_proof["recovery"]["observed_count"] == 59
    assert not learner.active_skill_versions


@pytest.mark.parametrize("skill", [ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION])
def test_native_upstream_recovery_keeps_current_entry_gate(progression, monkeypatch, skill):  # noqa: F811
    learner, _, _ = progression
    monkeypatch.setattr(learner, "entry_outcome_availability", lambda: {"qualified": True})
    if skill == ChallengerSkill.ENTRY:
        at = datetime.now(UTC) - timedelta(hours=2)
        model = qualified_model("recovery-entry", -0.2, 80).model_copy(
            update={
                "created_at": at,
                "configuration_fingerprint": learner.configuration_fingerprint(),
            }
        )
        learner._publish_entry_artifact(
            model,
            baseline_version=BASELINE_VERSION,
            evidence_started_at=at - timedelta(hours=1),
            evidence_ended_at=at,
        )
        learner.set_participation(True)
        artifact = learner.skill_artifacts[learner.active_skill_versions["entry"]]
    else:
        artifact = activate_first(learner, skill)
    learner._suspend_skill(skill, "degraded")
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(60):
        record_policy(learner, f"upstream-{index}", at + timedelta(seconds=index))
    if skill == ChallengerSkill.ENTRY:
        monkeypatch.setattr(learner, "entry_outcome_availability", lambda: {"qualified": False})
        learner._govern_skill_ensemble()
        assert not learner.active_skill_versions
        monkeypatch.setattr(learner, "entry_outcome_availability", lambda: {"qualified": True})
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {skill.value: artifact.version}


def test_out_of_order_and_duplicate_enrollment_does_not_expand_fixed_trial(progression):  # noqa: F811
    learner, _, _ = progression
    activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    at = datetime.now(UTC) + timedelta(minutes=2)
    episode = record_policy(learner, "first-original", at)
    learner._enroll_skill_recovery(episode)
    late = record_policy(learner, "old-arrival", at - timedelta(seconds=1))
    recovery = learner._current_skill_state(ChallengerSkill.EXIT).activation_proof["recovery"]
    assert [row["id"] for row in recovery["rows"]] == [episode.episode_id, late.episode_id]


def test_suspension_readout_does_not_write_or_expose_policy_ids(progression):  # noqa: F811
    learner, database, _ = progression
    activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    record_policy(learner, "private-policy", datetime.now(UTC) + timedelta(minutes=1))
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    before = database._conn.total_changes
    view = learner.skill_suspension_summary(state)
    assert view["reason"] == "degraded" and view["enrolled_count"] == 1
    assert "rows" not in view and "private-policy" not in str(view)
    assert database._conn.total_changes == before


@pytest.mark.parametrize("already_suspended", [False, True])
def test_legacy_exit_quarantine_timestamp_is_stable_across_restart(
    progression,  # noqa: F811
    already_suspended,
):
    learner, database, settings = progression
    artifact = activate_first(learner, ChallengerSkill.EXIT)
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    if already_suspended:
        learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    state.last_tournament = {"result": "promoted", "proof_version": "old"}
    database.save_challenger_skill_state(state)
    first = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    stamp = first._current_skill_state(ChallengerSkill.EXIT).suspended_at
    second = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    state = second._current_skill_state(ChallengerSkill.EXIT)
    assert state.suspended_at == stamp
    assert state.suspended_version == artifact.version
    assert state.suspension_reason == "exit_comparison_proof_requires_requalification"
    assert not second._recovery_allowed(state)
    assert not second.active_skill_versions


@pytest.mark.parametrize("bad_rows", [[None], ["bad-row"], [{"id": None}], "bad-list"])
def test_bad_saved_recovery_rows_do_not_interrupt_new_evidence(progression, bad_rows):  # noqa: F811
    learner, _, _ = progression
    activate_first(learner, ChallengerSkill.EXIT)
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    at = datetime.now(UTC) + timedelta(minutes=1)
    record_policy(learner, "before-corruption", at)
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    state.activation_proof["recovery"]["rows"] = bad_rows
    assert record_policy(learner, "after-corruption", at + timedelta(seconds=1))
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions


def test_same_upstream_version_in_a_new_reign_invalidates_recovery(progression):  # noqa: F811
    from test_participation_progression import native_champion

    learner, _, _ = progression
    activate_first(learner, ChallengerSkill.SIZING)
    artifact = native_champion(learner, ChallengerSkill.EXIT, datetime.now(UTC))
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(30):
        record_policy(learner, f"dependent-join-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions["exit"] == artifact.version
    learner._suspend_skill(ChallengerSkill.EXIT, "degraded")
    for index in range(60):
        record_policy(
            learner, f"dependent-recovery-{index}", at + timedelta(minutes=2, seconds=index)
        )
    upstream = learner._current_skill_state(ChallengerSkill.SIZING)
    upstream.joined_at += timedelta(seconds=1)
    learner._govern_skill_ensemble()
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    assert "exit" not in learner.active_skill_versions
    assert state.activation_proof["recovery"]["status"] == "context_changed"
