"""A rare downstream opportunity can age out; never select proof by its return."""

# ruff: noqa: F811 -- shared pytest fixture
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.models import ChallengerSkill
from test_participation_progression import native_champion, progression, record_policy  # noqa: F401


@pytest.mark.parametrize("new_vetoes, expected", [(970, 30), (990, 10), (1000, 0)])
@pytest.mark.parametrize("veto_return", [-0.9, 0.9])
def test_rolling_support_uses_recent_population_without_rescuing_old_winners(
    progression,
    new_vetoes,
    expected,
    veto_return,
):
    learner, _, _ = progression
    created = datetime.now(UTC) - timedelta(hours=2)
    manipulation = native_champion(learner, ChallengerSkill.MANIPULATION, created)
    sizing = native_champion(learner, ChallengerSkill.SIZING, created)
    learner.active_skill_versions = {"manipulation": manipulation.version}
    seed = record_policy(learner, "seed", created + timedelta(minutes=1))
    rows = []
    for index in range(30 + new_vetoes):
        at = seed.created_at + timedelta(seconds=index)
        row = seed.model_copy(
            deep=True,
            update={
                "episode_id": f"window-{index:04}",
                "mint": f"mint-{index}",
                "trajectory_key": f"trajectory-{index}",
                "idempotency_key": f"key-{index}",
                "entry_at": at,
                "created_at": at,
            },
        )
        for receipt in row.challenger_evaluations.values():
            receipt.evaluated_at = at
        upstream = row.challenger_evaluations[manipulation.version]
        upstream.in_distribution = True
        upstream.proposed_action = "support" if index < 30 else "veto"
        for checkpoint in row.checkpoints.values():
            checkpoint.observed_at = at + timedelta(seconds=checkpoint.horizon_seconds)
            if index >= 30:
                checkpoint.net_return = veto_return
        for trial in row.size_trials.values():
            for checkpoint in trial.checkpoints.values():
                checkpoint.observed_at = at + timedelta(seconds=checkpoint.horizon_seconds)
        rows.append(row)
    learner.evidence_episodes = {row.episode_id: row for row in rows}
    original = {key: row.model_dump_json() for key, row in learner.evidence_episodes.items()}
    proof = learner._skill_join_evidence(sizing, independent=True)
    assert proof["usable_count"] == proof["observed_count"] == expected
    assert proof["ready"] is (expected == 30)
    assert learner.active_skill_versions == {"manipulation": manipulation.version}
    assert original == {
        key: row.model_dump_json() for key, row in learner.evidence_episodes.items()
    }
