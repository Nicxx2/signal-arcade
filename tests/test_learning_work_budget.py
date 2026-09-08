import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import signal_arcade.intelligence.learning as learning_module
from signal_arcade.intelligence.learning import _policy_identity_key
from signal_arcade.models import RiskMode
from test_participation_progression import record_policy
from test_v1104_training_history import training_fixture


def test_status_reuses_training_count_only_within_this_response(settings, monkeypatch):
    learner, database, _ = training_fixture(settings, count=12)
    original = learner._training_rows
    calls = []

    def rows(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    try:
        expected = learner.evidence_lane_status()
        monkeypatch.setattr(learner, "_training_rows", rows)
        first = learner.status(demo_mode=False)
        assert first["evidence_lanes"] == expected
        assert len(calls) == 1
        for row in learner.observations.values():
            row.checkpoints.clear()
        calls.clear()
        second = learner.status(demo_mode=False)
        assert second["usable_outcome_count"] == 0
        assert second["evidence_lanes"][0]["usable_count"] == 0
        assert len(calls) == 1
    finally:
        database.close()


@pytest.mark.parametrize("wrong_mode", [False, True])
@pytest.mark.parametrize("wrong_configuration", [None, "", "other-fees"])
def test_evidence_lanes_recompute_a_summary_from_another_cohort(
    settings, wrong_mode, wrong_configuration
):
    learner, database, _ = training_fixture(settings, count=12)
    try:
        expected = learner.evidence_lane_status()
        result = learner.evidence_lane_status(
            training_summary=(
                RiskMode.SAFE if wrong_mode else RiskMode.BALANCED,
                wrong_configuration,
                999,
            )
        )
        assert result == expected
    finally:
        database.close()


def test_evidence_lanes_reject_other_risk_summary_even_with_matching_configuration(settings):
    learner, database, context = training_fixture(settings, count=12)
    try:
        expected = learner.evidence_lane_status()
        assert learner.evidence_lane_status(
            training_summary=(RiskMode.SAFE, context[0], 999)
        ) == expected
    finally:
        database.close()


@pytest.mark.parametrize("mode", [None, RiskMode.BALANCED])
@pytest.mark.parametrize("match_configuration", [False, True])
def test_training_selection_checks_policy_only_for_otherwise_usable_rows(
    settings, monkeypatch, mode, match_configuration
):
    learner, database, context = training_fixture(settings, count=1)
    try:
        base = learner.observations.pop("row-0")
        learner.observations.clear()
        labels = (
            "good-early",
            "other-risk",
            "other-config",
            "reserved",
            "pending",
            "unavailable",
            "incomplete",
            "other-source",
            "old-features",
            "old-baseline",
            "good-late",
        )
        rows = {}
        for index, label in enumerate(labels):
            row = base.model_copy(deep=True)
            row.mint = label
            row.observation_id = label
            row.created_at += timedelta(seconds=index)
            rows[label] = row
        rows["other-risk"].risk_mode = RiskMode.SAFE
        rows["other-config"].configuration_fingerprint = "another-config"
        rows["pending"].checkpoints.clear()
        rows["unavailable"].checkpoints["300"].net_return = None
        rows["unavailable"].checkpoints["300"].missing_reason = "route_unavailable"
        rows["incomplete"].features.clear()
        rows["other-source"].source_mode = "demo"
        rows["old-features"].feature_schema_version = "old-feature-contract"
        rows["old-baseline"].baseline_version = "old-baseline-contract"
        learner.observations.update(reversed(list(rows.items())))
        reserved = rows["reserved"]
        learner._policy_identities[_policy_identity_key(reserved)] = (
            reserved.created_at.isoformat(),
            "original-policy-episode",
        )
        checked = []
        original = learner._observation_has_policy_twin

        def check(row):
            checked.append(row.mint)
            return original(row)

        monkeypatch.setattr(learner, "_observation_has_policy_twin", check)
        actual = learner._training_rows(
            mode=mode,
            configuration_fingerprint=context[0],
            match_configuration=match_configuration,
        )
        expected = ["good-early"]
        if mode is None:
            expected.append("other-risk")
        if not match_configuration:
            expected.append("other-config")
        expected.append("good-late")
        assert [row.mint for row, _ in actual] == expected
        assert all(value == base.checkpoints["300"].net_return for _, value in actual)
        assert set(checked) == {*expected, "reserved"}
        assert len(checked) == len(expected) + 1
        assert "unavailable" in learner.observations
        assert learner.observations["unavailable"].checkpoints["300"].net_return is None
    finally:
        database.close()


def test_policy_digest_reuses_only_immutable_contract_material(settings, monkeypatch):
    learner, database, _ = training_fixture(settings, count=1)
    try:
        row = learner.observations["row-0"]
        row.mint = "digest-work-budget"
        learning_module._policy_identity_digest.cache_clear()
        calls = []
        original = learning_module._stable_digest

        def digest(value):
            calls.append(value)
            return original(value)

        monkeypatch.setattr(learning_module, "_stable_digest", digest)
        expected = hashlib.sha256(
            json.dumps(
                (
                    learning_module.LEARNING_EVIDENCE_SCHEMA_VERSION,
                    row.mint,
                    row.risk_mode.value,
                    row.configuration_fingerprint,
                    row.baseline_version,
                    row.feature_schema_version,
                ),
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        assert _policy_identity_key(row) == expected
        for index in range(5):
            # Mutable proof facts must never form a cached eligibility decision.
            row.checkpoints["300"].net_return = None if index % 2 else 0.1
            row.created_at += timedelta(seconds=1)
            row.observation_id = f"new-observation-{index}"
            assert _policy_identity_key(row) == expected
        assert len(calls) == 1
        for field, value in (
            ("mint", "another-mint"),
            ("risk_mode", RiskMode.SAFE),
            ("configuration_fingerprint", None),
            ("configuration_fingerprint", ""),
            ("baseline_version", "new-baseline"),
            ("feature_schema_version", "new-features"),
        ):
            changed = row.model_copy(update={field: value})
            assert _policy_identity_key(changed) != expected
        monkeypatch.setattr(learning_module, "LEARNING_EVIDENCE_SCHEMA_VERSION", "new-evidence")
        assert _policy_identity_key(row) != expected
        assert len(calls) == 8
    finally:
        database.close()


def test_policy_identity_cache_is_bounded_and_eviction_preserves_identity():
    digest = learning_module._policy_identity_digest
    digest.cache_clear()
    key = ("evidence", "first", "balanced", None, "baseline", "features")
    expected = digest(*key)
    try:
        limit = digest.cache_info().maxsize
        assert limit is not None and limit <= 16_384
        for index in range(limit + 3):
            digest("evidence", str(index), "balanced", None, "baseline", "features")
        assert digest.cache_info().currsize == limit
        misses = digest.cache_info().misses
        assert digest(*key) == expected
        assert digest.cache_info().misses == misses + 1  # Evicted material is recomputed exactly.
        with ThreadPoolExecutor(max_workers=4) as workers:
            assert list(workers.map(lambda _: digest(*key), range(32))) == [expected] * 32
        digest.cache_clear()  # A restart or cold cache does not change the durable identity.
        assert digest(*key) == expected
    finally:
        digest.cache_clear()


def test_warm_identity_digest_does_not_share_eligibility_between_learning_workspaces(settings):
    learner, database, context = training_fixture(settings, count=1)
    try:
        row = learner.observations["row-0"]
        database.save_learning_observation(row)
        key = _policy_identity_key(row)
        assert learner._training_rows() == [(row, row.checkpoints["300"].net_return)]
        # A workspace may predate a new reservation in the live owner. Only the pure digest
        # may be shared; the current owner's exclusion must take effect immediately.
        workspace = learning_module.LearningEngine(
            database, settings, configuration_fingerprint=lambda: context[0]
        )
        learner._policy_identities[key] = (row.created_at.isoformat(), "reserved-policy")
        assert _policy_identity_key(row) == key
        assert learner._training_rows() == []
        assert [item.mint for item, _ in workspace._training_rows()] == [row.mint]
        assert learner._training_rows() == []
    finally:
        database.close()


def test_warm_policy_digest_keeps_unknown_outcomes_and_rechecks_original_clock(settings):
    learner, database, _ = training_fixture(settings, count=0)
    try:
        episode = record_policy(learner, "warm-policy", datetime.now(UTC) - timedelta(hours=1))
        arguments = {
            "mode": learner.current_risk_mode,
            "configuration_fingerprint": learner.configuration_fingerprint(),
            "baseline_version": learner.baseline_version(),
        }
        assert learner._policy_evidence(**arguments) == [episode]
        key = _policy_identity_key(episode)
        old_cohort = learning_module._policy_evidence_cohort([episode])
        assert learner.entry_outcome_availability()["available_count"] == 1
        episode.checkpoints["300"].net_return = None
        episode.checkpoints["300"].missing_reason = "route_unavailable"
        assert _policy_identity_key(episode) == key
        assert learner._policy_evidence(**arguments) == [episode]
        assert learning_module._policy_evidence_cohort([episode]) != old_cohort
        availability = learner.entry_outcome_availability()
        assert availability["observed_count"] == 1
        assert availability["available_count"] == 0
        assert availability["minimum_fraction"] == 0.7
        assert not availability["qualified"]
        # Clock changes cannot reuse the original proof reservation, even on a cache hit.
        episode.entry_at += timedelta(microseconds=1)
        assert _policy_identity_key(episode) == key
        assert learner._policy_evidence(**arguments) == []
        assert learner._training_rows() == []  # The reserved Discovery twin stays excluded.
    finally:
        database.close()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_training_filter_rejects_nonfinite_features_without_losing_observation(settings, value):
    learner, database, _ = training_fixture(settings, count=1)
    try:
        row = learner.observations["row-0"]
        name = learning_module.FEATURE_NAMES[0]
        original = row.features[name]
        row.features[name] = value
        assert learner._training_rows() == []
        assert learner.observations[row.mint] is row
        row.features[name] = original
        assert learner._training_rows() == [(row, row.checkpoints["300"].net_return)]
    finally:
        database.close()
