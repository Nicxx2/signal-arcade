"""Reuse only the current pass's Policy population, never health or qualification results."""

import pytest
from signal_arcade.models import ChallengerSkill, RiskMode
from test_participation_progression import progression  # noqa: F401
from test_participation_progression import (
    test_exit_rejoins_after_sizing_with_fresh_proof_and_fresh_health as setup_combined,
)


@pytest.mark.parametrize(
    "change", ["none", "missing_exit_receipts", "harmful_sizing", "empty_policy"]
)
def test_governance_selects_once_but_rechecks_health_after_each_change(
    progression,  # noqa: F811
    monkeypatch,
    change,
):
    setup_combined(progression)
    learner, _, _ = progression
    active = dict(learner.active_skill_versions)
    before = {
        skill: learner._skill_health(ChallengerSkill(skill), version)
        for skill, version in active.items()
    }
    assert all(value["state"] == "healthy" for value in before.values())
    selected, checks = [], []
    select = learner._policy_evidence
    check = learner._skill_health

    def select_rows(**kwargs):
        selected.append(kwargs)
        return select(**kwargs)

    def health(skill, version, **kwargs):
        result = check(skill, version, **kwargs)
        checks.append((skill.value, result))
        return result

    monkeypatch.setattr(learner, "_policy_evidence", select_rows)
    monkeypatch.setattr(learner, "_skill_health", health)
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == active
    assert dict(checks) == before
    assert len(selected) == 1, "same Policy population was reselected for each active skill"

    if change == "empty_policy":
        learner.evidence_episodes.clear()
    for episode in learner.evidence_episodes.values():
        if change == "missing_exit_receipts":
            episode.challenger_evaluations.pop(active["exit"], None)
        elif change == "harmful_sizing":
            trial = episode.size_trials["0.5"]
            trial.checkpoints["300"].exit_value_lamports = trial.entry_cost_lamports // 10
    selected.clear()
    checks.clear()
    learner._govern_skill_ensemble()
    assert len(selected) == 1
    if change == "none":
        assert dict(checks) == before
        assert learner.active_skill_versions == active
    elif change == "empty_policy":
        assert all(result["observed_count"] == 0 for _, result in checks)
        assert all(result["state"] == "collecting" for _, result in checks)
        assert learner.active_skill_versions == active
    elif change == "missing_exit_receipts":
        assert dict(checks)["exit"]["state"] == "unverifiable"
        assert dict(checks)["exit"]["observed_count"] == 30
        assert dict(checks)["exit"]["usable_count"] == 0
        assert learner.active_skill_versions == {"sizing": active["sizing"]}
    else:
        assert checks[0][0] == "sizing" and checks[0][1]["state"] == "degraded"
        assert len(checks) == 1  # Stop at upstream harm; do not reuse old downstream authority.
        assert learner.active_skill_versions == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk_mode", RiskMode.SAFE),
        ("configuration_fingerprint", None),
        ("configuration_fingerprint", ""),
        ("baseline_version", "other-baseline"),
    ],
)
def test_health_population_never_crosses_an_artifact_contract(
    progression,  # noqa: F811
    monkeypatch,
    field,
    value,
):
    setup_combined(progression)
    learner, _, _ = progression
    policy_rows = {}
    version = learner.active_skill_versions["exit"]
    original = learner._skill_health(ChallengerSkill.EXIT, version, policy_rows=policy_rows)
    assert original["state"] == "healthy" and original["observed_count"] == 30
    artifact = learner.skill_artifacts[version]
    learner.skill_artifacts[version] = artifact.model_copy(update={field: value})
    expected = learner._skill_health(ChallengerSkill.EXIT, version)
    assert expected["observed_count"] == 0
    calls = []
    select = learner._policy_evidence

    def select_rows(**kwargs):
        calls.append(kwargs)
        return select(**kwargs)

    monkeypatch.setattr(learner, "_policy_evidence", select_rows)
    assert learner._skill_health(ChallengerSkill.EXIT, version, policy_rows=policy_rows) == expected
    assert learner._skill_health(ChallengerSkill.EXIT, version, policy_rows=policy_rows) == expected
    assert len(calls) == 1  # Empty populations are valid results for this exact contract.
    assert len(policy_rows) == 2
