"""Reduce repeated dashboard validation without retaining a proof or trading decision."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
import signal_arcade.intelligence.learning as learning_module
from signal_arcade.models import RiskMode
from test_v1104_training_history import training_fixture


def test_status_checks_each_discovery_feature_vector_once_per_response(settings, monkeypatch):
    learner, database, _ = training_fixture(settings, count=120)
    for index, row in enumerate(learner.observations.values()):
        if index % 10 == 0:
            row.features[learning_module.FEATURE_NAMES[0]] = float("nan")
        elif index % 10 == 1:
            row.features.pop(learning_module.FEATURE_NAMES[0])
    original = learning_module._observation_features_complete
    calls = Counter()

    def checked(row):
        calls[id(row)] += 1
        return original(row)

    try:
        expected = learner.status(demo_mode=False)
        monkeypatch.setattr(learning_module, "_observation_features_complete", checked)
        assert learner.status(demo_mode=False) == expected
        assert len(calls) == 120
        assert max(calls.values()) == 1
        calls.clear()
        assert learner.status(demo_mode=False) == expected
        assert len(calls) == 120 and max(calls.values()) == 1
    finally:
        database.close()


@pytest.mark.parametrize("change", ["features", "outcome", "policy", "risk", "configuration"])
def test_new_view_and_standalone_proof_recheck_changed_inputs(settings, change):
    learner, database, context = training_fixture(settings, count=120)
    try:
        before = learner.status(demo_mode=False)
        assert before["usable_outcome_count"] == 120
        for row in learner.observations.values():
            if change == "features":
                row.features[learning_module.FEATURE_NAMES[0]] = float("nan")
            elif change == "outcome":
                row.checkpoints["300"].net_return = None
                row.checkpoints["300"].missing_reason = "route_unavailable"
            elif change == "policy":
                learner._policy_identities[learning_module._policy_identity_key(row)] = (
                    row.created_at.isoformat(),
                    "reserved-proof",
                )
        if change == "risk":
            learner.current_risk_mode = RiskMode.SAFE
        if change == "configuration":
            context[0] = "another-configuration"
        direct = learner.entry_outcome_availability()
        current = learner.status(demo_mode=False)
        assert current["usable_outcome_count"] == 0
        assert current["entry_outcome_availability"] == direct
        assert not direct["qualified"]
        assert direct["minimum_fraction"] == 0.70
        if change == "outcome":
            assert direct["observed_count"] == 120  # Genuine failures remain in the denominator.
        assert getattr(learner._status_policy_cache, "features", None) is None
    finally:
        database.close()


def test_failed_status_clears_its_temporary_validation_and_selection(settings, monkeypatch):
    learner, database, _ = training_fixture(settings, count=12)
    original = learner.evidence_lane_status

    def fail(**kwargs):
        raise RuntimeError("interrupted view")

    try:
        monkeypatch.setattr(learner, "evidence_lane_status", fail)
        with pytest.raises(RuntimeError, match="interrupted view"):
            learner.status(demo_mode=False)
        assert getattr(learner._status_policy_cache, "features", None) is None
        assert getattr(learner._status_policy_cache, "rows", None) is None
        for row in learner.observations.values():
            row.features.clear()
        monkeypatch.setattr(learner, "evidence_lane_status", original)
        assert learner.status(demo_mode=False)["usable_outcome_count"] == 0
    finally:
        database.close()


def test_standalone_learning_paths_keep_the_original_validation_path(settings, monkeypatch):
    learner, database, _ = training_fixture(settings, count=12)

    def unexpected(row):
        raise AssertionError("non-dashboard work entered the display reuse path")

    try:
        monkeypatch.setattr(learner, "_complete_discovery_features", unexpected)
        assert len(learner._training_rows()) == 12
        assert learner.entry_outcome_availability()["observed_count"] == 12
        assert learner.evidence_lane_status()[0]["usable_count"] == 12
    finally:
        database.close()


def test_status_feature_reuse_never_crosses_worker_threads(settings, monkeypatch):
    learner, database, _ = training_fixture(settings, count=12)
    entered, release = Event(), Event()
    original = learner.evidence_lane_status

    def hold(**kwargs):
        entered.set()
        assert release.wait(3)
        return original(**kwargs)

    try:
        monkeypatch.setattr(learner, "evidence_lane_status", hold)
        with ThreadPoolExecutor(max_workers=1) as worker:
            future = worker.submit(learner.status, demo_mode=False)
            try:
                assert entered.wait(3)
                assert getattr(learner._status_policy_cache, "features", None) is None
                assert len(learner._training_rows()) == 12
            finally:
                release.set()
            assert future.result(timeout=3)["usable_outcome_count"] == 12
    finally:
        release.set()
        database.close()
