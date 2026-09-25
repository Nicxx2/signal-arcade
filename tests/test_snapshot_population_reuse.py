"""Only immutable-within-response population facts may be reused by the dashboard."""

import pytest
from signal_arcade.intelligence.learning import _policy_identity_key
from test_v1104_training_history import training_fixture


@pytest.mark.parametrize("ending", ["normal", "error", "nested"])
def test_twin_reuse_is_response_local_and_restores_after_every_exit(settings, monkeypatch, ending):
    learner, db, _ = training_fixture(settings, count=1)
    observation = next(iter(learner.observations.values()))
    current = learner._current_observation_has_policy_twin
    calls = []

    def read(row):
        calls.append(row.mint)
        return current(row)

    def render(**_kwargs):
        assert learner._observation_has_policy_twin(observation) == current(observation)
        assert learner._observation_has_policy_twin(observation) == current(observation)
        if ending == "error":
            raise ValueError("render failed")
        if ending == "nested":
            with monkeypatch.context() as inner:
                inner.setattr(
                    learner,
                    "_status",
                    lambda **_: {"twin": learner._observation_has_policy_twin(observation)},
                )
                learner.status(demo_mode=False)
            learner._observation_has_policy_twin(observation)
        return {}

    monkeypatch.setattr(learner, "_current_observation_has_policy_twin", read)
    monkeypatch.setattr(learner, "_status", render)
    try:
        if ending == "error":
            with pytest.raises(ValueError, match="render failed"):
                learner.status(demo_mode=False)
        else:
            learner.status(demo_mode=False)
        assert len(calls) == (2 if ending == "nested" else 1)
        assert learner._status_policy_cache.twins is None
        assert not learner._observation_has_policy_twin(observation)
        learner._policy_identities[_policy_identity_key(observation)] = ("later", "proof")
        assert learner._observation_has_policy_twin(observation)
        assert len(calls) == (4 if ending == "nested" else 3)
    finally:
        db.close()


def test_real_status_matches_uncached_population_facts(settings, monkeypatch):
    learner, db, _ = training_fixture(settings, count=100)
    try:
        original = learner._current_observation_has_policy_twin
        # Compare every result during a real status assembly, not selected output fields.
        calls = []

        def wrapper(row):
            result = original(row)
            calls.append(row.mint)
            return result

        monkeypatch.setattr(learner, "_current_observation_has_policy_twin", wrapper)
        learner.status(demo_mode=False)
        assert calls and len(calls) == len(set(calls))
        assert len(calls) <= len(learner.observations)
        assert learner._status_policy_cache.twins is None
    finally:
        db.close()
