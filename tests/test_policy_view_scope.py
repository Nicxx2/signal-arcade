from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.models import ChallengerSkill, RiskMode
from test_participation_progression import native_champion, progression, record_policy  # noqa: F401
from test_participation_progression import (
    test_exit_rejoins_after_sizing_with_fresh_proof_and_fresh_health as setup_combined,
)


def test_status_reuses_only_selection_and_rechecks_changed_evidence(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    now = datetime.now(UTC)
    row = record_policy(learner, "one", now)
    calls = []
    original = learner._select_policy_evidence

    def select(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(learner, "_select_policy_evidence", select)
    first = learner.status(demo_mode=False)
    assert len(calls) == 1
    calls.clear()
    row.qualification_eligible = False
    second = learner.status(demo_mode=False)
    assert len(calls) == 1
    assert second["evidence_contract"]["collection_started_at"] is None
    assert first["evidence_contract"]["collection_started_at"] == row.entry_at.isoformat()
    # A standalone authority read must never inherit the dashboard's selection.
    learner._policy_evidence(
        mode=RiskMode.BALANCED,
        configuration_fingerprint=learner.configuration_fingerprint(),
        baseline_version=learner.baseline_version(),
    )
    assert len(calls) == 2


def test_view_cache_is_cleared_after_exception_and_isolated_between_threads(
    progression,  # noqa: F811
    monkeypatch,
):
    learner, _, _ = progression
    original = learner._status

    def broken(**kwargs):
        assert learner._status_policy_cache.rows == {}
        raise RuntimeError("view failed")

    monkeypatch.setattr(learner, "_status", broken)
    with pytest.raises(RuntimeError, match="view failed"):
        learner.status(demo_mode=False)
    assert learner._status_policy_cache.rows is None
    monkeypatch.setattr(learner, "_status", original)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: learner.status(demo_mode=False), range(2)))
    assert results[0]["evidence_contract"] == results[1]["evidence_contract"]


def test_tournament_selection_does_not_survive_the_pass(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    now = datetime.now(UTC)
    for skill in (ChallengerSkill.SIZING, ChallengerSkill.EXIT):
        champion = native_champion(learner, skill, now)
        state = learner._current_skill_state(skill)
        learner._register_skill_artifact(
            champion.model_copy(update={"version": champion.version + "-contender"}),
            state.cohort_key,
        )
    record_policy(learner, "one", now + timedelta(seconds=1))
    calls = []
    original = learner._policy_evidence

    def select(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(learner, "_policy_evidence", select)
    learner._advance_entry_tournaments()
    assert len(calls) == 1
    calls.clear()
    learner.evidence_episodes.clear()
    learner._advance_entry_tournaments()
    assert len(calls) == 1
    assert all(state.common_forward_count == 0 for state in learner.skill_states.values())


def test_outcome_boundary_shares_selection_but_never_delays_health(progression, monkeypatch):  # noqa: F811
    setup_combined(progression)
    learner, _, _ = progression
    active = dict(learner.active_skill_versions)
    state = learner._current_skill_state(ChallengerSkill.SIZING)
    learner._register_skill_artifact(
        learner.skill_artifacts[active["sizing"]].model_copy(update={"version": "new-sizing"}),
        state.cohort_key,
    )
    calls = []
    select = learner._select_policy_evidence

    def selected(**kwargs):
        calls.append(kwargs)
        return select(**kwargs)

    monkeypatch.setattr(learner, "_select_policy_evidence", selected)
    learner._advance_primary_outcomes(set(), outcomes_changed=True)
    assert len(calls) == 1
    assert learner.active_skill_versions == active
    assert getattr(learner._status_policy_cache, "rows", None) is None
    for episode in learner.evidence_episodes.values():
        episode.challenger_evaluations.pop(active["exit"], None)
    calls.clear()
    learner._advance_primary_outcomes(set(), outcomes_changed=True)
    assert len(calls) == 1
    assert learner.active_skill_versions == {"sizing": active["sizing"]}
    assert learner._current_skill_state(ChallengerSkill.EXIT).suspended_version == active["exit"]


def test_outcome_selection_scope_restores_owner_even_after_failure(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    outer = {"outer": []}
    learner._status_policy_cache.rows = outer

    def failed():
        assert learner._status_policy_cache.rows == {}
        raise RuntimeError("injected governance failure")

    monkeypatch.setattr(learner, "_govern_active_model", failed)
    with pytest.raises(RuntimeError, match="injected governance"):
        learner._advance_primary_outcomes(set(), outcomes_changed=True)
    assert learner._status_policy_cache.rows is outer
