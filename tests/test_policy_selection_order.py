"""Filtering before ordering must preserve independent chronological Policy proof."""

# ruff: noqa: F811 -- shared fixture

from datetime import UTC, datetime, timedelta, timezone

import pytest
from signal_arcade.models import LearningEvidenceLane
from test_participation_progression import progression, record_policy  # noqa: F401


@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_history_keeps_earliest_identity_ties_missing_and_negative_outcomes(
    progression,
    reverse,  # noqa: F811
):
    learner, _, _ = progression
    now = datetime.now(UTC) - timedelta(hours=2)
    prototype = record_policy(learner, "seed", now)
    rows = []
    for index in range(1005):
        row = prototype.model_copy(
            deep=True,
            update={
                "episode_id": f"policy-{index:04}",
                "mint": f"mint-{index}",
                "entry_at": now + timedelta(seconds=index),
            },
        )
        if index % 2:
            row.checkpoints["300"].net_return = None
        rows.append(row)
        # A later successful attempt must never replace the first missing outcome.
        later = row.model_copy(deep=True, update={"episode_id": f"later-{index:04}"})
        later.entry_at += timedelta(days=1)
        later.checkpoints["300"].net_return = 0.9
        rows.append(later)
        rows.append(
            row.model_copy(
                update={
                    "episode_id": f"execution-{index:04}",
                    "lane": LearningEvidenceLane.EXECUTION,
                }
            )
        )
        rows.append(
            row.model_copy(
                update={"episode_id": f"foreign-{index:04}", "configuration_fingerprint": "foreign"}
            )
        )
    # Equal instants with different offsets must use the unchanged episode-ID tie-break.
    tie = rows[-4].model_copy(deep=True, update={"episode_id": "a-tie"})
    tie.entry_at = tie.entry_at.astimezone(timezone(timedelta(hours=1)))
    rows.append(tie)
    naive = tie.model_copy(
        update={"episode_id": "0-naive", "mint": "naive", "entry_at": now.replace(tzinfo=None)}
    )
    rows.append(naive)
    learner.evidence_episodes = {
        row.episode_id: row for row in (reversed(rows) if reverse else rows)
    }
    original = {key: row.model_dump_json() for key, row in learner.evidence_episodes.items()}
    chosen = learner._select_policy_evidence(
        mode=learner.current_risk_mode,
        configuration_fingerprint=learner.configuration_fingerprint(),
        baseline_version=learner.baseline_version(),
    )
    assert len(chosen) == 1000
    assert [row.mint for row in chosen] == [f"mint-{i}" for i in range(5, 1005)]
    assert chosen[-1].episode_id == "a-tie"
    assert all(row.checkpoints["300"].net_return in (None, -0.1) for row in chosen)
    assert sum(row.checkpoints["300"].net_return is None for row in chosen) == 500
    assert original == {
        key: row.model_dump_json() for key, row in learner.evidence_episodes.items()
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("qualification_eligible", False),
        ("synthetic", True),
        ("baseline_actionable", False),
        ("season_id", None),
    ],
)
def test_excluded_earlier_row_does_not_hide_eligible_later_row(progression, field, value):  # noqa: F811
    learner, _, _ = progression
    now = datetime.now(UTC) - timedelta(hours=2)
    first = record_policy(learner, "seed", now)
    earlier = first.model_copy(deep=True, update={"episode_id": "earlier", field: value})
    earlier.entry_at -= timedelta(seconds=1)
    learner.evidence_episodes[earlier.episode_id] = earlier
    chosen = learner._select_policy_evidence(
        mode=learner.current_risk_mode,
        configuration_fingerprint=learner.configuration_fingerprint(),
        baseline_version=learner.baseline_version(),
    )
    assert [row.episode_id for row in chosen] == [first.episode_id]
