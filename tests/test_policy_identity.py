from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import LearningCheckpoint, LearningEvidenceStatus
from test_learning import make_decision, make_state, policy_episode_for


def enroll(learner, mint, at, *, season="one", actionable=True):
    decision = make_decision(at, mint)
    decision.configuration_fingerprint = "identity-test"
    decision.season_id = season
    assert learner.register(decision, make_state(mint), live=True, evaluation_actionable=actionable)
    return learner.observations[mint]


@pytest.mark.parametrize("legacy_return", [None, 0.2])
@pytest.mark.parametrize("changed", ["feature_schema_version", "baseline_version", "source_mode"])
def test_current_coverage_excludes_old_contract_without_erasing_current_failures(
    settings,
    legacy_return,
    changed,
):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test")
    at = datetime.now(UTC)
    for index in range(90):
        observation = enroll(learner, str(index), at + timedelta(seconds=index), actionable=False)
        observation.checkpoints["300"] = LearningCheckpoint(
            horizon_seconds=300,
            observed_at=at + timedelta(minutes=10),
            net_return=legacy_return if index < 80 else (0.1 if index < 87 else None),
        )
        if index < 80:
            setattr(
                observation,
                changed,
                {
                    "feature_schema_version": "challenger-features-v4",
                    "baseline_version": "baseline-old",
                    "source_mode": "demo",
                }[changed],
            )
        database.save_learning_observation(observation)
    for engine in (
        learner,
        LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test"),
    ):
        coverage = engine.entry_outcome_availability()
        assert coverage["observed_count"] == 10
        assert coverage["available_count"] == 7
        assert coverage["availability_fraction"] == 0.7
        assert not coverage["qualified"]  # Sample minimum remains unchanged.
    database.close()


def test_policy_identity_survives_pruning_restart_and_later_seasons(settings):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test")
    at = datetime.now(UTC) - timedelta(hours=2)
    observation = enroll(learner, "repeated", at)
    first = policy_episode_for(learner, "repeated")
    first.status = LearningEvidenceStatus.COMPLETE
    database.save_learning_evidence_episode(first)
    observation.checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=at + timedelta(minutes=5),
        net_return=0.3,
    )
    database.save_learning_observation(observation)
    enroll(learner, "other", at + timedelta(minutes=30))
    other = policy_episode_for(learner, "other")
    other.status = LearningEvidenceStatus.COMPLETE
    database.save_learning_evidence_episode(other)
    assert database.prune_learning_evidence(1) == [first.episode_id]
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=lambda: "identity-test"
    )
    assert restarted._observation_has_policy_twin(restarted.observations["repeated"])
    assert not restarted._training_rows()
    enroll(restarted, "repeated", at + timedelta(hours=1), season="two")
    evidence = restarted._policy_evidence(
        mode=restarted.current_risk_mode,
        configuration_fingerprint="identity-test",
        baseline_version=restarted.baseline_version(),
    )
    assert [item.mint for item in evidence] == ["other"]
    restarted.request_current_training()
    job = restarted.prepare_next_training()
    assert job is not None
    restarted.fit_training_job(job)
    assert not job.workspace._training_rows()
    assert [
        item.mint
        for item in job.workspace._policy_evidence(
            mode=restarted.current_risk_mode,
            configuration_fingerprint="identity-test",
            baseline_version=restarted.baseline_version(),
        )
    ] == ["other"]
    database.close()


def test_schema_15_backfill_keeps_earliest_eligible_identity(settings):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test")
    at = datetime.now(UTC)
    enroll(learner, "one", at)
    first = policy_episode_for(learner, "one").episode_id
    enroll(learner, "one", at + timedelta(hours=1), season="two")
    database._conn.execute("DROP TABLE learning_policy_identities")
    database._conn.execute("PRAGMA user_version=15")
    database._conn.commit()
    database.close()
    migrated = Database(settings.database_path)
    restarted = LearningEngine(
        migrated, settings, configuration_fingerprint=lambda: "identity-test"
    )
    assert [
        item.episode_id
        for item in restarted._policy_evidence(
            mode=restarted.current_risk_mode,
            configuration_fingerprint="identity-test",
            baseline_version=restarted.baseline_version(),
        )
    ] == [first]
    migrated.close()


@pytest.mark.parametrize("restart", [False, True])
def test_same_season_pruned_identity_cannot_be_recreated_as_new_proof(settings, restart):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test")
    at = datetime.now(UTC) - timedelta(hours=3)
    enroll(learner, "repeated", at)
    first = policy_episode_for(learner, "repeated")
    first.status = LearningEvidenceStatus.COMPLETE
    first.checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300, observed_at=at + timedelta(minutes=5), net_return=None
    )
    database.save_learning_evidence_episode(first)
    enroll(learner, "other", at + timedelta(minutes=1))
    other = policy_episode_for(learner, "other")
    other.status = LearningEvidenceStatus.COMPLETE
    database.save_learning_evidence_episode(other)
    assert database.prune_learning_evidence(1) == [first.episode_id]
    if restart:
        learner = LearningEngine(
            database, settings, configuration_fingerprint=lambda: "identity-test"
        )
    else:
        learner.evidence_episodes.pop(first.episode_id)
        learner._evidence_episode_ids_by_mint.pop(first.mint)
        learner._policy_identities.clear()  # A pruned cache must consult its durable reservation.
    enroll(learner, "repeated", at + timedelta(hours=2))
    repeated = policy_episode_for(learner, "repeated")
    assert repeated.episode_id == first.episode_id
    repeated.checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300, observed_at=at + timedelta(hours=2, minutes=5), net_return=0.5
    )
    database.save_learning_evidence_episode(repeated)
    for engine in (
        learner,
        LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test"),
    ):
        assert not engine._policy_evidence(
            mode=engine.current_risk_mode,
            configuration_fingerprint="identity-test",
            baseline_version=engine.baseline_version(),
            not_before=at + timedelta(hours=1),
        )
        assert engine.entry_outcome_availability()["available_count"] == 0
        assert not engine._training_rows()
        engine.request_current_training()
        job = engine.prepare_next_training()
        assert job is not None
        assert all(
            item.mint != "repeated"
            for item in job.workspace._policy_evidence(
                mode=engine.current_risk_mode,
                configuration_fingerprint="identity-test",
                baseline_version=engine.baseline_version(),
            )
        )
    database.close()


@pytest.mark.parametrize("clock", ["equivalent_offset", "naive", "malformed", "different"])
def test_policy_identity_compares_instants_and_rejects_ambiguous_clocks(settings, clock):
    from datetime import timezone

    from signal_arcade.intelligence.learning import _policy_identity_key

    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test")
    at = datetime.now(UTC)
    enroll(learner, "one", at)
    episode = policy_episode_for(learner, "one")
    value = {
        "equivalent_offset": at.astimezone(timezone(timedelta(hours=1))).isoformat(),
        "naive": at.replace(tzinfo=None).isoformat(),
        "malformed": "bad-clock",
        "different": (at + timedelta(microseconds=1)).isoformat(),
    }[clock]
    learner._policy_identities[_policy_identity_key(episode)] = (value, episode.episode_id)
    evidence = learner._policy_evidence(
        mode=learner.current_risk_mode,
        configuration_fingerprint="identity-test",
        baseline_version=learner.baseline_version(),
    )
    assert bool(evidence) == (clock == "equivalent_offset")
    database.close()


def test_durable_identity_orders_offsets_and_microseconds_and_keeps_reservations(settings):
    database = Database(settings.database_path)
    first = "2026-09-07T01:00:00.000001+01:00"
    later = "2026-09-07T00:00:00.000002+00:00"
    # Simulate an older stored offset representation, not a current normalized writer.
    with database._conn:
        database._conn.execute(
            "INSERT INTO learning_policy_identities VALUES(?,?,?)", ("key", first, "first")
        )
    database.remember_policy_identities([("key", later, "later")])
    assert database.policy_identities({"key"})["key"] == (
        "2026-09-07T00:00:00.000001+00:00",
        "first",
    )
    database.remember_policy_identities([("blank", "", ""), ("blank", later, "eligible")])
    assert database.policy_identities({"blank"})["blank"] == (later, "eligible")
    with database._conn:
        database._conn.execute(
            "INSERT INTO learning_policy_identities VALUES(?,?,?)", ("bad", "invalid", "reserved")
        )
    database.remember_policy_identities([("bad", later, "new")])
    assert database.policy_identities({"bad"})["bad"] == ("invalid", "reserved")
    database.close()
