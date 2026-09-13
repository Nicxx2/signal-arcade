from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.champion_impact import build_impact
from signal_arcade.models import (
    ChallengerEvaluationReceipt,
    ChallengerSizeTrial,
    LearningCheckpoint,
    LearningEvidenceEpisode,
)
from test_participation_progression import progression  # noqa: F401
from test_participation_progression import (
    test_exit_rejoins_after_sizing_with_fresh_proof_and_fresh_health as setup_combined,
)

NOW = datetime(2026, 9, 13, 10, tzinfo=UTC)


def rows_for(skills=("sizing",), count=30):
    versions = {s: f"champion-{s}" for s in skills}
    rows = []
    for index in range(count):
        at = NOW - timedelta(hours=3) + timedelta(seconds=index)
        row = LearningEvidenceEpisode(
            episode_id=f"episode-{index}",
            idempotency_key=f"key-{index}",
            trajectory_key=f"trajectory-{index}",
            mint=f"mint-{index}",
            symbol="TEST",
            lane="policy",
            status="complete",
            created_at=at,
            entry_at=at,
            qualification_eligible=True,
            season_id="season",
            season_profile_fingerprint="profile",
            risk_mode="balanced",
            baseline_version="baseline",
            feature_schema_version="features",
            baseline_action="enter",
            baseline_actionable=True,
            active_skill_versions=versions,
        )
        for h, retained in ((300, 0.8), (600, 0.6), (1200, 0.5)):
            row.checkpoints[str(h)] = LearningCheckpoint(
                horizon_seconds=h,
                observed_at=at + timedelta(seconds=h),
                net_return=retained - 1,
            )
        for multiplier in (0.5, 1, 1.5, 2):
            cost = int(multiplier * 1000)
            trial = ChallengerSizeTrial(
                multiplier=multiplier,
                budget_lamports=cost,
                entry_cost_lamports=cost,
                token_units=cost,
                eligible_at_entry=True,
            )
            for h, retained in ((300, 0.8), (600, 0.6), (1200, 0.5)):
                trial.checkpoints[str(h)] = LearningCheckpoint(
                    horizon_seconds=h,
                    observed_at=at + timedelta(seconds=h),
                    exit_value_lamports=int(cost * retained),
                )
            row.size_trials[f"{multiplier:g}"] = trial
        for skill, version in versions.items():
            row.challenger_evaluations[version] = ChallengerEvaluationReceipt(
                artifact_version=version,
                skill=skill,
                evaluated_at=at,
                in_distribution=True,
                proposed_action={"sizing": "0.5", "exit": "300"}.get(skill, "support"),
                baseline_actionable=True,
                parameters={"bounded_multiplier": 0.5, "bounds_policy": "sizing-authority-v1"},
            )
        rows.append(row)
    return rows, versions


def report(rows, versions, **kwargs):
    options = dict(
        versions=versions,
        since=NOW - timedelta(hours=4),
        season_id="season",
        profile="profile",
        normal_hold=600,
        now=NOW,
    )
    options.update(kwargs)
    return build_impact(rows, **options)


def comparison(data, subject):
    return next(x for x in data["comparisons"] if x["subject"] == subject)


def test_smaller_losses_are_an_advantage_but_not_positive_returns():
    rows, versions = rows_for()
    original = [r.model_dump() for r in rows]
    result = comparison(report(rows, versions), "sizing")
    assert result["state"] == "positive"
    assert result["reference_mean"] == pytest.approx(-0.2)
    assert result["supported_mean"] == pytest.approx(-0.1)
    assert result["mean_advantage"] == pytest.approx(0.1)
    assert result["lower_bound"] == pytest.approx(0.1)
    assert result["usable_count"] == 30
    assert [r.model_dump() for r in rows] == original


def test_team_uses_same_opportunities_and_quotes_instead_of_adding_skill_deltas():
    rows, versions = rows_for(("sizing", "exit"))
    result = report(rows, versions)
    team = comparison(result, "team")
    sizing = comparison(result, "sizing")
    exit_timing = comparison(result, "exit")
    assert team["reference_mean"] == pytest.approx(-0.4)
    assert team["supported_mean"] == pytest.approx(-0.1)
    assert team["mean_advantage"] == pytest.approx(0.3)
    assert sizing["mean_advantage"] == pytest.approx(0.1)
    assert exit_timing["mean_advantage"] == pytest.approx(0.1)
    assert team["mean_advantage"] != sizing["mean_advantage"] + exit_timing["mean_advantage"]


def test_overlapping_vetoes_count_once_and_downstream_roles_are_not_reached():
    rows, versions = rows_for(("entry", "manipulation", "sizing", "exit"))
    for row in rows:
        for skill in ("entry", "manipulation"):
            row.challenger_evaluations[versions[skill]].proposed_action = "veto"
    result = report(rows, versions)
    assert comparison(result, "team")["mean_advantage"] == pytest.approx(0.4)
    for skill in ("manipulation", "sizing", "exit"):
        assert comparison(result, skill)["observed_count"] == 0
        assert comparison(result, skill)["not_reached_count"] == 30


@pytest.mark.parametrize("skill", ["entry", "manipulation", "sizing", "exit"])
def test_unfamiliar_proposals_preserve_reference(skill):
    rows, versions = rows_for((skill,))
    for row in rows:
        receipt = row.challenger_evaluations[versions[skill]]
        receipt.in_distribution = False
        if skill in ("entry", "manipulation"):
            receipt.proposed_action = "veto"
    value = comparison(report(rows, versions), skill)
    assert value["mean_advantage"] == 0
    assert value["state"] == "uncertain"


@pytest.mark.parametrize("failure", ["receipt", "timestamp", "role", "clamp", "route", "baseline"])
def test_missing_or_unverifiable_pairs_remain_in_denominator(failure):
    rows, versions = rows_for()
    for row in rows[:10]:
        receipt = row.challenger_evaluations[versions["sizing"]]
        if failure == "receipt":
            row.challenger_evaluations.clear()
        elif failure == "timestamp":
            receipt.evaluated_at += timedelta(seconds=1)
        elif failure == "role":
            receipt.skill = "exit"
        elif failure == "clamp":
            receipt.parameters.clear()
        elif failure == "route":
            row.size_trials["0.5"].checkpoints["300"].missing_reason = "route_unavailable"
        else:
            row.size_trials["1"].eligible_at_entry = False
    value = comparison(report(rows, versions), "sizing")
    assert value["observed_count"] == 30
    assert value["usable_count"] == 20
    assert value["coverage"] == pytest.approx(2 / 3)
    assert value["state"] == "collecting"


def test_pending_is_separate_and_zero_samples_do_not_make_zero_profit():
    rows, versions = rows_for()
    for row in rows:
        row.status = "pending"
        row.checkpoints.clear()
        row.size_trials.clear()
    value = comparison(report(rows, versions), "sizing")
    assert value["pending_count"] == 30
    assert value["observed_count"] == value["usable_count"] == 0
    assert value["mean_advantage"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("season_id", "other"),
        ("season_profile_fingerprint", "other"),
        ("active_skill_versions", {"sizing": "replacement"}),
        ("synthetic", True),
        ("baseline_actionable", False),
        ("qualification_eligible", False),
        ("lane", "execution"),
    ],
)
def test_other_contexts_and_non_actionable_rows_cannot_gain_credit(field, value):
    rows, versions = rows_for()
    rows = [r.model_copy(update={field: value}) for r in rows]
    assert comparison(report(rows, versions), "sizing")["observed_count"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"since": None},
        {"since": NOW},
        {"profile": None},
        {"season_id": None},
        {"normal_hold": 450},
    ],
)
def test_missing_context_and_new_activation_cannot_reuse_old_evidence(changes):
    rows, versions = rows_for()
    result = report(rows, versions, **changes)
    assert all(x["observed_count"] == 0 for x in result["comparisons"])


def test_latest_window_keeps_losses_and_unknowns_and_order_is_stable():
    rows, versions = rows_for(count=90)
    for row in rows[-20:]:
        row.challenger_evaluations.clear()
    expected = report(rows, versions)
    value = comparison(expected, "sizing")
    assert value["observed_count"] == 60
    assert value["usable_count"] == 40
    assert value["state"] == "collecting"
    assert report(list(reversed(rows)), versions) == expected
    assert report(rows + rows[-10:], versions) == expected


def test_negative_and_uncertain_results_are_not_called_helpful():
    rows, versions = rows_for()
    for row in rows:
        row.challenger_evaluations[versions["sizing"]].parameters["bounded_multiplier"] = 2
    assert comparison(report(rows, versions), "sizing")["state"] == "negative"
    for row in rows[::2]:
        row.size_trials["2"].checkpoints["300"].exit_value_lamports = 2000
    assert comparison(report(rows, versions), "sizing")["state"] == "uncertain"


def test_later_duplicate_cannot_replace_an_unavailable_original():
    rows, versions = rows_for(count=1)
    original = rows[0]
    later = original.model_copy(deep=True)
    later.episode_id = "later"
    later.created_at += timedelta(seconds=1)
    later.challenger_evaluations[versions["sizing"]].evaluated_at = later.created_at
    original.challenger_evaluations.clear()
    for order in ([original, later], [later, original]):
        value = comparison(report(order, versions), "sizing")
        assert value["observed_count"] == 1
        assert value["usable_count"] == 0


@pytest.mark.parametrize(
    "kind", ["nan", "future", "before_entry", "premature", "naive", "wrong_horizon"]
)
def test_invalid_outcomes_are_unknown_pairs_not_dashboard_failures(kind):
    rows, versions = rows_for(("entry",))
    for row in rows:
        point = row.checkpoints["300"]
        if kind == "nan":
            point.net_return = float("nan")
        elif kind == "future":
            point.observed_at = NOW + timedelta(days=1)
        elif kind == "before_entry":
            point.observed_at = row.created_at - timedelta(seconds=1)
        elif kind == "premature":
            point.observed_at = row.created_at + timedelta(seconds=299)
        elif kind == "naive":
            point.observed_at = point.observed_at.replace(tzinfo=None)
        else:
            point.horizon_seconds = 600
    value = comparison(report(rows, versions), "entry")
    assert value["observed_count"] == 30
    assert value["usable_count"] == 0


def test_real_policy_receipts_share_status_population_without_changing_authority(
    progression,  # noqa: F811
    monkeypatch,
):
    from signal_arcade.intelligence import learning

    setup_combined(progression)
    learner, database, _ = progression
    rows = list(learner.evidence_episodes.values())
    latest = max(row.created_at for row in rows) + timedelta(hours=1)
    for row in rows:
        row.season_profile_fingerprint = "profile"
    season_id = rows[-1].season_id
    assert season_id

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return latest

    monkeypatch.setattr(learning, "datetime", Clock)
    before = {key: state.model_dump() for key, state in learner.skill_states.items()}
    versions = dict(learner.active_skill_versions)
    selected = []
    select = learner._select_policy_evidence

    def tracked(**kwargs):
        selected.append(1)
        return select(**kwargs)

    def no_write(*args, **kwargs):
        pytest.fail("rendering impact attempted to write learning state")

    monkeypatch.setattr(learner, "_select_policy_evidence", tracked)
    monkeypatch.setattr(database, "save_challenger_skill_state", no_write)
    monkeypatch.setattr(database, "save_learning_evidence_episode", no_write)
    snapshot = learner.status(demo_mode=False, impact_context=(season_id, "profile", 600))
    result = snapshot["champion_impact"]
    assert result["state"] == "available"
    assert comparison(result, "team")["usable_count"] == 30
    assert comparison(result, "sizing")["usable_count"] == 30
    assert comparison(result, "exit")["usable_count"] == 30
    assert len(selected) == 1
    assert learner.active_skill_versions == versions
    assert before == {key: state.model_dump() for key, state in learner.skill_states.items()}
    for context, demo in (
        (("new-season", "profile", 600), False),
        ((season_id, "profile", 600), True),
    ):
        result = learner.status(demo_mode=demo, impact_context=context)["champion_impact"]
        assert all(x["observed_count"] == 0 for x in result["comparisons"])


@pytest.mark.parametrize("failure", ["zero_cost", "negative_cost", "wrong_size", "entry_failure"])
def test_inconsistent_sizing_trial_is_unavailable(failure):
    rows, versions = rows_for()
    for row in rows:
        trial = row.size_trials["0.5"]
        if failure == "zero_cost":
            trial.entry_cost_lamports = 0
        elif failure == "negative_cost":
            trial.entry_cost_lamports = -100
        elif failure == "wrong_size":
            trial.multiplier = 2.0
        else:
            trial.entry_missing_reason = "route_unavailable"
    value = comparison(report(rows, versions), "sizing")
    assert value["observed_count"] == 30
    assert value["usable_count"] == 0


def test_work_is_bounded_for_maximum_population_and_overlapping_vetoes(monkeypatch):
    from signal_arcade.intelligence import champion_impact

    rows, versions = rows_for(("entry", "manipulation", "sizing", "exit"), count=1000)
    for row in rows:
        row.challenger_evaluations[versions["entry"]].proposed_action = "veto"
    calls = []
    original = champion_impact._values

    def tracked(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(champion_impact, "_values", tracked)
    result = report(rows, versions)
    assert len(result["comparisons"]) == 5
    assert len(calls) <= 5 * 1000
    assert all(x["observed_count"] <= 60 for x in result["comparisons"])
    assert comparison(result, "sizing")["not_reached_count"] == 1000


def test_restart_rebuilds_same_view_and_reactivation_starts_fresh(
    progression,  # noqa: F811
    monkeypatch,
):
    from signal_arcade.intelligence import learning
    from signal_arcade.models import ChallengerSkill

    setup_combined(progression)
    learner, database, settings = progression
    rows = list(learner.evidence_episodes.values())
    at = max(row.created_at for row in rows) + timedelta(hours=1)
    for row in rows:
        row.season_profile_fingerprint = "profile"
        database.save_learning_evidence_episode(row)
    context = (rows[-1].season_id, "profile", 600)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr(learning, "datetime", Clock)
    before = learner.status(demo_mode=False, impact_context=context)["champion_impact"]
    restarted = learning.LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    after = restarted.status(demo_mode=False, impact_context=context)["champion_impact"]
    assert after == before
    assert comparison(after, "team")["usable_count"] == 30
    state = restarted._current_skill_state(ChallengerSkill.EXIT)
    state.joined_at = at
    fresh = restarted.status(demo_mode=False, impact_context=context)["champion_impact"]
    assert all(item["observed_count"] == 0 for item in fresh["comparisons"])
