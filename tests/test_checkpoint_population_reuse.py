"""Per-pass row selection must not cache outcomes, authority or future evidence."""

from datetime import UTC, datetime, timedelta

import pytest
import signal_arcade.intelligence.learning as module
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import ChallengerSkill
from test_learning import make_decision, make_state
from test_participation_progression import native_champion, record_policy


def reference_sample(learner, states, now):
    # v1.10.11 order: select once, then govern immediately after each mint's update.
    return sum(
        learner.observe_market(states[mint], now, live=True, cached=True)
        for mint in learner.due_checkpoint_mints(
            states, now, limit=20, fresh=True, diagnostics=learner.collection_diagnostics
        )
    )


def facts(learner):
    return {
        "observations": [x.model_dump(mode="json") for x in learner.observations.values()],
        "episodes": [x.model_dump(mode="json") for x in learner.evidence_episodes.values()],
        "states": [
            x.model_dump(mode="json", exclude={"updated_at"}) for x in learner.skill_states.values()
        ],
        "active": dict(learner.active_skill_versions),
        "mode": learner.mode,
        "identities": dict(learner._policy_identities),
        "outcomes": dict(learner.context_outcome_counts),
        "requests": dict(learner._training_requests),
    }


@pytest.mark.parametrize("restart", [False, True])
def test_cached_and_reference_passes_keep_every_checkpoint_and_governance_boundary(
    settings, tmp_path, monkeypatch, restart
):
    start = datetime(2026, 9, 26, 12, tzinfo=UTC)
    clock = [start]

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0] if tz is not None else clock[0].replace(tzinfo=None)

    monkeypatch.setattr(module, "datetime", FixedDateTime)
    results, selections = [], []
    for cached in (False, True):
        clock[0] = start
        configured = settings.model_copy(update={"data_dir": tmp_path / str(cached)})
        database = Database(configured.database_path)
        database.set_setting("demo_mode", False)
        learner = LearningEngine(database, configured, configuration_fingerprint=lambda: "same")
        for skill in (ChallengerSkill.MANIPULATION, ChallengerSkill.SIZING):
            native_champion(learner, skill, start - timedelta(hours=1))
        learner.set_participation(True)
        states = {}
        for index in range(36):
            mint = f"pass-{index}"
            decision = make_decision(start, mint)
            decision.configuration_fingerprint = "same"
            state = make_state(mint)
            state.real_quote_reserves = 30_000_000_000
            assert learner.register(
                decision, state, live=True, evaluation_actionable=index % 7 != 6
            )
            states[mint] = state
        # Shared mints still advance every original episode clock. A retained original
        # identity prevents these later episodes from manufacturing independent proof.
        original = next(iter(learner.evidence_episodes.values()))
        for index, offset in enumerate((0, 0, 13)):
            extra = original.model_copy(
                deep=True,
                update={
                    "episode_id": f"shared-{index}",
                    "idempotency_key": f"shared-idempotency-{index}",
                    "trajectory_key": f"shared-trajectory-{index}",
                    "entry_at": start + timedelta(seconds=offset),
                },
            )
            database.save_learning_evidence_episode(extra)
            learner.remember_committed_evidence(extra)
        boundaries, selected = [], []

        def attach_observers(target, checkpoint_facts, selection_calls):
            original_govern = target._govern_skill_ensemble
            original_select = target._select_policy_evidence

            def govern():
                original_govern()
                checkpoint_facts.append(facts(target))

            def select(**kwargs):
                selection_calls.append(True)
                return original_select(**kwargs)

            monkeypatch.setattr(target, "_govern_skill_ensemble", govern)
            monkeypatch.setattr(target, "_select_policy_evidence", select)

        attach_observers(learner, boundaries, selected)
        try:
            # Both sides of deadlines, repeated and backward times, plus complete closure.
            for second in (60, 60, 59, 150, 150.000001, 180, 300, 300, 600, 1200, 1291):
                clock[0] = start + timedelta(seconds=second)
                for index, state in enumerate(states.values()):
                    state.last_reserve_at = clock[0] - timedelta(seconds=90 if index == 1 else 0)
                    state.last_event_at = state.last_reserve_at
                    state.real_quote_reserves = 1 if index == 2 else 30_000_000_000
                for _ in range(2):  # More eligible mints than the unchanged 20-mint budget.
                    if cached:
                        learner.sample_due_checkpoints(states, clock[0], live=True)
                    else:
                        reference_sample(learner, states, clock[0])
                learner.expire_checkpoints(clock[0], states=states)
                assert getattr(learner._status_policy_cache, "rows", None) is None
                assert getattr(learner._status_policy_cache, "checkpoint_rows", None) is None
                if restart and second == 600:
                    learner = LearningEngine(
                        database, configured, configuration_fingerprint=lambda: "same"
                    )
                    attach_observers(learner, boundaries, selected)
            results.append((boundaries, facts(learner)))
            selections.append(len(selected))
        finally:
            database.close()
    assert results[0] == results[1]
    assert selections[1] < selections[0]


@pytest.mark.parametrize(
    "change", ["enroll", "replace", "prune", "prune_failure", "new_pass", "nested"]
)
def test_population_changes_and_failure_cannot_reuse_old_membership(settings, monkeypatch, change):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "same")
    at = datetime(2026, 9, 26, tzinfo=UTC)
    episode = record_policy(learner, "original", at)
    kwargs = {
        "mode": learner.current_risk_mode,
        "configuration_fingerprint": "same",
        "baseline_version": learner.baseline_version(),
    }
    try:
        with learner._policy_selection_scope():
            assert learner._policy_evidence(**kwargs) == [episode]
            # Outcomes are live values, not cached qualification or health results.
            episode.checkpoints["300"].net_return = None
            assert learner._policy_evidence(**kwargs)[0].checkpoints["300"].net_return is None
            if change == "enroll":
                other = record_policy(learner, "new", at + timedelta(seconds=1))
                assert learner._policy_evidence(**kwargs) == [episode, other]
            elif change == "replace":
                replacement = episode.model_copy(update={"qualification_eligible": False})
                database.save_learning_evidence_episode(replacement)
                learner.remember_committed_evidence(replacement)
                assert learner._policy_evidence(**kwargs) == []
            elif change == "prune_failure":

                def fail(*args):
                    raise RuntimeError("injected prune failure")

                monkeypatch.setattr(database, "prune_learning_observations", fail)
                with pytest.raises(RuntimeError, match="injected"):
                    learner._prune_complete_history()
                assert learner._status_policy_cache.rows == {}
            elif change == "prune":
                monkeypatch.setattr(
                    database, "prune_learning_evidence", lambda *args: [episode.episode_id]
                )
                learner._prune_complete_history()
                assert learner._policy_evidence(**kwargs) == []
            elif change == "nested":
                with learner._policy_selection_scope():
                    replacement = episode.model_copy(update={"qualification_eligible": False})
                    learner.remember_committed_evidence(replacement)
                assert learner._policy_evidence(**kwargs) == []
        assert getattr(learner._status_policy_cache, "rows", None) is None
        if change == "new_pass":
            episode.features.clear()
            with learner._policy_selection_scope():
                assert learner._policy_evidence(**kwargs) == []
    finally:
        database.close()


def test_only_explicit_checkpoint_owner_can_be_reused_and_failure_restores_it(settings):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    try:
        with learner._policy_selection_scope(checkpoint_pass=True):
            owner = learner._status_policy_cache.rows
            with learner._policy_selection_scope(reuse=True):
                assert learner._status_policy_cache.rows is owner
            with learner._policy_selection_scope():
                view = learner._status_policy_cache.rows
                assert view is not owner
                with (
                    pytest.raises(RuntimeError, match="injected"),
                    learner._policy_selection_scope(reuse=True),
                ):
                    assert learner._status_policy_cache.rows is not view
                    assert learner._status_policy_cache.checkpoint_rows is None
                    raise RuntimeError("injected nested failure")
                assert learner._status_policy_cache.rows is view
                assert learner._status_policy_cache.checkpoint_rows is None
            with learner._policy_selection_scope(reuse=True):
                assert learner._status_policy_cache.rows is owner
                assert learner._status_policy_cache.checkpoint_rows is owner
        assert learner._status_policy_cache.rows is None
        assert learner._status_policy_cache.checkpoint_rows is None
    finally:
        database.close()
