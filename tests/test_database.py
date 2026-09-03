from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from signal_arcade.database import (
    MAX_STATISTICAL_MODEL_ARTIFACT_BYTES,
    SCHEMA_VERSION,
    TERMINAL_POLICY_VERSION,
    Database,
)
from signal_arcade.models import (
    ChallengerChampionEvent,
    ChallengerSkill,
    ChallengerSkillArtifact,
    ChallengerSkillState,
    DecisionAction,
    EventKind,
    LearningEvidenceEpisode,
    LearningEvidenceLane,
    LearningEvidenceStatus,
    MarketEvent,
    PaperOrder,
    RiskMode,
    Side,
    StatisticalModelFamily,
)


def test_events_are_deduplicated(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    event = MarketEvent(
        event_id="same",
        source="test",
        kind=EventKind.CREATE,
        mint="mint",
        received_at=datetime.now(UTC),
    )
    assert database.append_event(event) is True
    assert database.append_event(event) is False
    assert len(database.recent_events()) == 1
    database.close()


def test_health_check_does_not_wait_for_active_database_work(tmp_path: Path) -> None:
    database = Database(tmp_path / "health.sqlite3")
    lock_owned = threading.Event()
    release_lock = threading.Event()

    def hold_database_lock() -> None:
        with database._lock:  # noqa: SLF001 - intentional maintenance-contention simulation
            lock_owned.set()
            release_lock.wait(timeout=5)

    worker = threading.Thread(target=hold_database_lock)
    worker.start()
    assert lock_owned.wait(timeout=2)
    try:
        assert database.health_check() is True
    finally:
        release_lock.set()
        worker.join(timeout=2)
        database.close()


def test_health_check_does_not_wait_for_active_dashboard_reader(tmp_path: Path) -> None:
    database = Database(tmp_path / "reader-health.sqlite3")
    lock_owned = threading.Event()
    release_lock = threading.Event()

    def hold_reader_lock() -> None:
        with database._reader_lock:  # noqa: SLF001 - intentional read-contention simulation
            lock_owned.set()
            release_lock.wait(timeout=5)

    worker = threading.Thread(target=hold_reader_lock)
    worker.start()
    assert lock_owned.wait(timeout=2)
    try:
        assert database.health_check() is True
    finally:
        release_lock.set()
        worker.join(timeout=2)
        database.close()


def test_read_connection_does_not_wait_for_maintenance_writer_lock(tmp_path: Path) -> None:
    database = Database(tmp_path / "wal-reader.sqlite3")
    database.set_setting("example", {"ready": True})
    lock_owned = threading.Event()
    release_lock = threading.Event()

    def hold_writer_lock() -> None:
        with database._lock:  # noqa: SLF001 - intentional maintenance-contention simulation
            lock_owned.set()
            release_lock.wait(timeout=5)

    worker = threading.Thread(target=hold_writer_lock)
    worker.start()
    assert lock_owned.wait(timeout=2)
    try:
        assert database.get_setting("example") == {"ready": True}
        assert database.list_decisions(30) == []
        assert database.list_fills(30) == []
        assert database.compact_equity_history() == []
    finally:
        release_lock.set()
        worker.join(timeout=2)
        database.close()


def test_recent_event_startup_query_uses_global_time_index_and_upgrades_v3(
    tmp_path: Path,
) -> None:
    path = tmp_path / "upgrade.sqlite3"
    database = Database(path)
    database._conn.execute(  # noqa: SLF001 - simulate the previous shipped schema
        "DROP INDEX idx_market_events_received_at"
    )
    database._conn.execute("PRAGMA user_version=3")  # noqa: SLF001
    database._conn.commit()  # noqa: SLF001
    database.close()

    upgraded = Database(path)
    indexes = {
        row[1]
        for row in upgraded._conn.execute(  # noqa: SLF001 - verify migration artifact
            "PRAGMA index_list(market_events)"
        )
    }
    plan = [
        row[3]
        for row in upgraded._conn.execute(  # noqa: SLF001 - verify startup query plan
            "EXPLAIN QUERY PLAN SELECT * FROM market_events ORDER BY received_at DESC LIMIT 20000"
        )
    ]
    assert "idx_market_events_received_at" in indexes
    assert any("idx_market_events_received_at" in step for step in plan)
    assert not any("TEMP B-TREE" in step for step in plan)
    assert (  # noqa: SLF001
        upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    )
    upgraded.close()


def test_v10_migration_preserves_completed_history_and_upgrades_only_current_boundary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v9-season-history.sqlite3"
    database = Database(path)
    database.initialize_portfolio("season-legacy", 1_000_000_000, "SOL")
    database.reset_paper_state(
        {
            "ending_equity_minor": 900_000_000,
            "last_known_ending_equity_minor": 900_000_000,
            "peak_equity_minor": 1_000_000_000,
            "realized_pnl_minor": -100_000_000,
            "net_pnl_minor": -100_000_000,
            "total_fees_minor": 1_000_000,
            "closed_trades": 1,
            "wins": 0,
            "losses": 1,
            "break_even": 0,
            "ending_drawdown_fraction": 0.1,
            "open_positions": 0,
            "meaningful_activity": True,
        }
    )
    database.initialize_portfolio("season-current", 500_000_000, "USDC")
    database.close()

    legacy = sqlite3.connect(path)
    for column in (
        "accounting_status",
        "terminal_policy_version",
        "boundary_type",
        "meaningful_activity",
        "write_off_count",
        "write_off_entry_minor",
    ):
        legacy.execute(f"ALTER TABLE paper_seasons DROP COLUMN {column}")
    legacy.execute("PRAGMA user_version=9")
    legacy.commit()
    legacy.close()

    upgraded = Database(path)
    seasons = upgraded.list_paper_seasons()
    assert seasons[0]["status"] == "completed"
    assert seasons[0]["accounting_status"] == "legacy"
    assert seasons[0]["terminal_policy_version"] == "legacy-v1"
    assert seasons[0]["net_pnl_minor"] == -100_000_000
    assert seasons[0]["comparable"] is False
    assert seasons[1]["status"] == "current"
    assert seasons[1]["accounting_status"] == "current"
    assert seasons[1]["terminal_policy_version"] == TERMINAL_POLICY_VERSION
    assert seasons[1]["boundary_type"] == "open"
    assert upgraded.ledger_balance("cash") == 500_000_000
    upgraded.close()


def test_v11_adds_multiskill_challenger_without_rewriting_legacy_learning(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v10-challenger.sqlite3"
    database = Database(path)
    legacy_payload = '{"version":"legacy-proof"}'
    database._conn.execute(  # noqa: SLF001 - seed an immutable legacy artifact
        "INSERT INTO learning_models VALUES(?,?,?,?)",
        ("legacy-proof", datetime.now(UTC).isoformat(), 0, legacy_payload),
    )
    database._conn.execute("PRAGMA user_version=10")  # noqa: SLF001
    database._conn.commit()  # noqa: SLF001
    database.close()

    upgraded = Database(path)
    artifact = ChallengerSkillArtifact(
        version="challenger-entry-v1",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="config-v1",
        baseline_version="baseline-v1.2",
        feature_schema_version="features-v1",
        qualified=True,
    )
    state = ChallengerSkillState(
        cohort_key="balanced:config-v1:baseline-v1.2:features-v1",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="config-v1",
        baseline_version="baseline-v1.2",
        feature_schema_version="features-v1",
        latest_candidate_version=artifact.version,
        champion_version=artifact.version,
        champion_journey=[
            ChallengerChampionEvent(
                event_id="champion-event-first",
                skill=ChallengerSkill.ENTRY,
                kind="first_champion",
                candidate_version=artifact.version,
                champion_version=artifact.version,
            )
        ],
    )
    upgraded.save_challenger_artifact(artifact)
    upgraded.save_challenger_artifact(artifact)
    with pytest.raises(ValueError, match="different data"):
        upgraded.save_challenger_artifact(artifact.model_copy(update={"qualified": False}))
    testing_artifact = artifact.model_copy(
        update={"version": "challenger-entry-testing", "created_at": datetime.now(UTC)}
    )
    latest_artifact = artifact.model_copy(
        update={"version": "challenger-entry-latest", "created_at": datetime.now(UTC)}
    )
    upgraded.save_challenger_artifact(testing_artifact)
    upgraded.save_challenger_artifact(latest_artifact)
    state.testing_version = testing_artifact.version
    state.latest_candidate_version = latest_artifact.version
    upgraded.save_challenger_skill_state(state)

    assert {item.version for item in upgraded.list_challenger_artifacts()} == {
        artifact.version,
        testing_artifact.version,
        latest_artifact.version,
    }
    assert upgraded.list_challenger_skill_states() == [state]
    raw_state = json.loads(
        upgraded._conn.execute(  # noqa: SLF001 - verify rollback-readable storage contract
            "SELECT record_json FROM challenger_skill_states"
        ).fetchone()[0]
    )
    assert "champion_journey" not in raw_state
    assert (
        upgraded._conn.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM settings WHERE key LIKE 'challenger_champion_journey_v1:%'"
        ).fetchone()[0]
        == 1
    )
    assert (
        upgraded._conn.execute(  # noqa: SLF001
            "SELECT record_json FROM learning_models WHERE version='legacy-proof'"
        ).fetchone()[0]
        == legacy_payload
    )
    assert upgraded.storage_stats(force=True)["challenger_skill_artifacts"] == 3
    assert upgraded.prune_challenger_artifacts(1) == []
    assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION  # noqa: SLF001
    upgraded.close()


def test_v13_adds_bounded_digest_verified_statistical_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "v12-statistical-artifacts.sqlite3"
    legacy = Database(path)
    legacy.initialize_portfolio("season-v1.9.2", 1_000_000_000, "USDC")
    legacy.set_setting("v1.9.2-upgrade-marker", {"preserved": True})
    legacy_artifact = ChallengerSkillArtifact(
        version="v1.9.2-entry-champion",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="v1.9.2-config",
        baseline_version="baseline-v1.5",
        feature_schema_version="challenger-features-v3",
        qualified=True,
    )
    legacy_state = ChallengerSkillState(
        cohort_key="v1.9.2-entry-cohort",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="v1.9.2-config",
        baseline_version="baseline-v1.5",
        feature_schema_version="challenger-features-v3",
        latest_candidate_version=legacy_artifact.version,
        champion_version=legacy_artifact.version,
    )
    legacy.save_challenger_artifact(legacy_artifact)
    legacy.save_challenger_skill_state(legacy_state)
    legacy._conn.execute("DROP TABLE statistical_model_artifacts")  # noqa: SLF001
    legacy._conn.execute("PRAGMA user_version=12")  # noqa: SLF001
    legacy._conn.commit()  # noqa: SLF001
    legacy.close()

    upgraded = Database(path)
    assert upgraded.get_setting("v1.9.2-upgrade-marker") == {"preserved": True}
    assert upgraded.get_setting("season_id") == "season-v1.9.2"
    assert upgraded.get_setting("quote_currency") == "USDC"
    assert upgraded.ledger_balance("cash") == 1_000_000_000
    current_season = upgraded.current_paper_season()
    assert current_season is not None
    assert current_season["season_id"] == "season-v1.9.2"
    assert upgraded.list_challenger_artifacts() == [legacy_artifact]
    assert upgraded.list_challenger_skill_states() == [legacy_state]
    payload = b'{"learner":{"type":"bounded-test"}}'
    digest = hashlib.sha256(payload).hexdigest()
    now = datetime.now(UTC)
    upgraded.save_statistical_model_artifact(
        version="nonlinear-test-v1",
        family="xgboost",
        payload_format="json",
        payload_digest=digest,
        created_at=now,
        payload=payload,
    )
    upgraded.save_statistical_model_artifact(
        version="nonlinear-test-v1",
        family="xgboost",
        payload_format="json",
        payload_digest=digest,
        created_at=now,
        payload=payload,
    )
    loaded = upgraded.load_statistical_model_artifact("nonlinear-test-v1")
    assert loaded is not None
    assert loaded["payload"] == payload
    assert loaded["payload_digest"] == digest
    assert upgraded.storage_stats(force=True)["statistical_model_artifacts"] == 1
    assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == 13  # noqa: SLF001

    with pytest.raises(ValueError, match="digest"):
        upgraded.save_statistical_model_artifact(
            version="bad-digest",
            family="xgboost",
            payload_format="json",
            payload_digest="0" * 64,
            created_at=now,
            payload=payload,
        )
    with pytest.raises(ValueError, match="size"):
        upgraded.save_statistical_model_artifact(
            version="oversized",
            family="xgboost",
            payload_format="json",
            payload_digest="0" * 64,
            created_at=now,
            payload=b"x" * (MAX_STATISTICAL_MODEL_ARTIFACT_BYTES + 1),
        )

    upgraded._conn.execute(  # noqa: SLF001 - simulate on-disk corruption after commit
        "UPDATE statistical_model_artifacts SET payload=? WHERE version=?",
        (b"corrupt", "nonlinear-test-v1"),
    )
    upgraded._conn.commit()  # noqa: SLF001
    with pytest.raises(ValueError, match="digest"):
        upgraded.load_statistical_model_artifact("nonlinear-test-v1")
    upgraded.close()


def test_embedded_champion_journey_is_migrated_to_rollback_safe_sidecar(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "embedded-champion-journey.sqlite3")
    event = ChallengerChampionEvent(
        event_id="embedded-event",
        skill=ChallengerSkill.ENTRY,
        kind="first_champion",
        candidate_version="embedded-champion",
        champion_version="embedded-champion",
    )
    state = ChallengerSkillState(
        cohort_key="balanced:embedded",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="embedded",
        baseline_version="baseline-v1.2",
        feature_schema_version="features-v2",
        champion_version="embedded-champion",
        pending_versions=["embedded-pending"],
        champion_journey=[event],
    )
    database._conn.execute(  # noqa: SLF001 - seed the short-lived embedded format
        "INSERT INTO challenger_skill_states VALUES(?,?,?,?)",
        (
            state.cohort_key,
            state.skill.value,
            state.updated_at.isoformat(),
            state.model_dump_json(),
        ),
    )
    database._conn.commit()  # noqa: SLF001

    assert database.list_challenger_skill_states() == [state]
    normalized = json.loads(
        database._conn.execute(  # noqa: SLF001
            "SELECT record_json FROM challenger_skill_states"
        ).fetchone()[0]
    )
    assert "champion_journey" not in normalized
    assert "pending_versions" not in normalized
    assert database.list_challenger_skill_states()[0].champion_journey == [event]
    assert database.list_challenger_skill_states()[0].pending_versions == ["embedded-pending"]
    database.close()


def test_nonlinear_challenger_record_and_payload_commit_atomically(tmp_path: Path) -> None:
    database = Database(tmp_path / "challenger-payload.sqlite3")
    payload = b'{"learner":{"type":"bounded-test"}}'
    digest = hashlib.sha256(payload).hexdigest()
    artifact = ChallengerSkillArtifact(
        version="nonlinear-challenger-v1",
        skill=ChallengerSkill.ENTRY,
        model_family=StatisticalModelFamily.XGBOOST,
        implementation_version="xgboost-test",
        recipe_version="test-v1",
        payload_format="json",
        payload_digest=digest,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="payload-config",
        baseline_version="baseline-v1.4",
        feature_schema_version="challenger-features-v4",
    )

    database.save_challenger_artifact_with_payload(artifact, payload)
    database.save_challenger_artifact_with_payload(artifact, payload)

    assert database.list_challenger_artifacts() == [artifact]
    stored = database.load_statistical_model_artifact(artifact.version)
    assert stored is not None and stored["payload"] == payload
    with pytest.raises(ValueError, match="digest"):
        database.save_challenger_artifact_with_payload(artifact, b"different")
    assert database.list_challenger_artifacts() == [artifact]
    database.close()


def test_challenger_pruning_preserves_artifacts_referenced_by_durable_journey(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "journey-pruning.sqlite3")
    now = datetime.now(UTC)
    champion = ChallengerSkillArtifact(
        version="journey-champion",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="journey-config",
        baseline_version="baseline-v1.4",
        feature_schema_version="challenger-features-v4",
        qualified=True,
        created_at=now,
    )
    old_contender = champion.model_copy(
        update={"version": "journey-old-contender", "created_at": now - timedelta(days=1)}
    )
    disposable = champion.model_copy(
        update={"version": "journey-disposable", "created_at": now - timedelta(days=2)}
    )
    for artifact in (champion, old_contender, disposable):
        database.save_challenger_artifact(artifact)
    state = ChallengerSkillState(
        cohort_key="journey-cohort",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="journey-config",
        baseline_version="baseline-v1.4",
        feature_schema_version="challenger-features-v4",
        latest_candidate_version=champion.version,
        champion_version=champion.version,
        champion_journey=[
            ChallengerChampionEvent(
                event_id="journey-defence",
                occurred_at=now,
                skill=ChallengerSkill.ENTRY,
                kind="defended",
                candidate_version=old_contender.version,
                previous_champion_version=champion.version,
                champion_version=champion.version,
            )
        ],
    )
    database.save_challenger_skill_state(state)

    assert database.prune_challenger_artifacts(1) == [disposable.version]
    assert {item.version for item in database.list_challenger_artifacts()} == {
        champion.version,
        old_contender.version,
    }
    database.close()


def test_ledger_rejects_unbalanced_transactions(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    with pytest.raises(ValueError, match="not balanced"):
        database.append_ledger("bad", [("cash", 100, 0, "bad")])
    database.append_ledger(
        "good",
        [("cash", 100, 0, "fund"), ("capital", 0, 100, "fund")],
    )
    assert database.ledger_balance("cash") == 100
    assert database.health_check()
    database.close()


def test_portfolio_initialization_rolls_back_every_effect_on_failure(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database._conn.executescript(  # noqa: SLF001 - intentional storage fault injection
        """
        CREATE TRIGGER reject_portfolio_setting BEFORE INSERT ON settings
        WHEN NEW.key = 'portfolio_initialized'
        BEGIN SELECT RAISE(ABORT, 'injected setup failure'); END;
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="injected setup failure"):
        database.initialize_portfolio("initial-test", 1_000_000_000, "USDC")

    assert database.ledger_balance("cash") == 0
    assert database.equity_history() == []
    assert database.get_setting("portfolio_initialized") is None
    database.close()


def test_reset_retains_market_evidence(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.append_event(
        MarketEvent(event_id="e1", source="test", kind=EventKind.MARKET, mint="mint")
    )
    database.append_ledger("fund", [("cash", 10, 0, "fund"), ("capital", 0, 10, "fund")])
    database.reset_paper_state()
    assert len(database.recent_events()) == 1
    assert database.ledger_balance("cash") == 0
    database.close()


def test_reset_archives_the_season_before_starting_the_next_one(tmp_path: Path) -> None:
    database = Database(tmp_path / "seasons.sqlite3")
    database.initialize_portfolio("season-one", 1_000_000_000, "SOL")

    current = database.list_paper_seasons()
    assert [(row["season_number"], row["status"]) for row in current] == [(1, "current")]

    database.reset_paper_state(
        {
            "ending_equity_minor": 1_120_000_000,
            "last_known_ending_equity_minor": 1_120_000_000,
            "peak_equity_minor": 1_200_000_000,
            "realized_pnl_minor": 120_000_000,
            "net_pnl_minor": 120_000_000,
            "total_fees_minor": 2_000_000,
            "closed_trades": 4,
            "wins": 3,
            "losses": 1,
            "break_even": 0,
            "ending_drawdown_fraction": 0.066,
            "open_positions": 0,
            "meaningful_activity": True,
        }
    )
    archived = database.list_paper_seasons()[0]
    assert archived["status"] == "completed"
    assert archived["ended_at"] is not None
    assert archived["net_pnl_minor"] == 120_000_000
    assert archived["wins"] == 3
    assert archived["accounting_status"] == "complete"
    assert archived["comparable"] is True
    assert database.ledger_balance("cash") == 0

    database.initialize_portfolio("season-two", 500_000_000, "SOL")
    seasons = database.list_paper_seasons()
    assert [(row["season_number"], row["status"]) for row in seasons] == [
        (1, "completed"),
        (2, "current"),
    ]
    database.close()


def test_initialized_portfolio_cannot_reset_without_a_durable_season_summary(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "safe-reset.sqlite3")
    database.initialize_portfolio("season-safe", 1_000_000_000, "SOL")

    with pytest.raises(RuntimeError, match="summarized before reset"):
        database.reset_paper_state()

    assert database.ledger_balance("cash") == 1_000_000_000
    assert database.list_paper_seasons()[0]["status"] == "current"
    database.close()


def test_reset_cannot_retire_inventory_without_matching_audit_records(tmp_path: Path) -> None:
    database = Database(tmp_path / "unresolved-audit.sqlite3")
    database.initialize_portfolio("season-audit", 1_000_000_000, "SOL")
    summary = {
        "ending_equity_minor": 900_000_000,
        "last_known_ending_equity_minor": 950_000_000,
        "peak_equity_minor": 1_000_000_000,
        "realized_pnl_minor": 0,
        "net_pnl_minor": -100_000_000,
        "total_fees_minor": 0,
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "break_even": 0,
        "ending_drawdown_fraction": 0.1,
        "open_positions": 1,
    }

    with pytest.raises(ValueError, match="must match unresolved inventory"):
        database.reset_paper_state(summary)

    assert database.get_setting("portfolio_initialized") is True
    assert database.get_setting("season_id") == "season-audit"
    assert database.ledger_balance("cash") == 1_000_000_000
    assert database.list_paper_seasons()[0]["status"] == "current"
    database.close()


def test_reset_rejects_a_writeoff_without_confirmed_route_evidence(tmp_path: Path) -> None:
    database = Database(tmp_path / "writeoff-proof.sqlite3")
    database.initialize_portfolio("season-proof", 1_000_000_000, "SOL")
    summary = {
        "ending_equity_minor": 900_000_000,
        "last_known_ending_equity_minor": 950_000_000,
        "peak_equity_minor": 1_000_000_000,
        "realized_pnl_minor": 0,
        "net_pnl_minor": -100_000_000,
        "total_fees_minor": 0,
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "break_even": 0,
        "ending_drawdown_fraction": 0.1,
        "open_positions": 1,
        "meaningful_activity": True,
    }
    unsupported = {
        "position_id": "unsupported-position",
        "mint": "unsupported-mint",
        "symbol": "NOPE",
        "was_executed": False,
        "terminal_disposition": "write_off",
        "terminal_evidence": {},
    }

    with pytest.raises(ValueError, match="requires confirmed route evidence"):
        database.reset_paper_state(summary, unresolved_positions=[unsupported])

    assert database.get_setting("portfolio_initialized") is True
    assert database.list_paper_seasons()[0]["status"] == "current"
    assert database.ledger_balance("cash") == 1_000_000_000
    database.close()


def execution_episode(
    now: datetime, *, episode_id: str = "execution-one"
) -> LearningEvidenceEpisode:
    return LearningEvidenceEpisode(
        episode_id=episode_id,
        idempotency_key=episode_id,
        lane=LearningEvidenceLane.EXECUTION,
        trajectory_key=episode_id,
        mint="mint-retired",
        symbol="RETIRED",
        created_at=now,
        entry_at=now,
        entry_fill_id="entry-fill",
        season_id="season-one",
        risk_mode=RiskMode.BALANCED,
        baseline_version="baseline-test",
        feature_schema_version="features-test",
        baseline_action=DecisionAction.ENTER,
        baseline_actionable=True,
        entry_account_minor=100,
        total_fee_account_minor=2,
    )


def unresolved_episode_inventory(
    now: datetime,
    *,
    disposition: str,
) -> dict[str, object]:
    item: dict[str, object] = {
        "position_id": "position-retired",
        "entry_fill_id": "entry-fill",
        "mint": "mint-retired",
        "symbol": "RETIRED",
        "was_executed": False,
        "terminal_disposition": disposition,
    }
    if disposition == "write_off":
        item["terminal_evidence"] = {
            "policy": "two-fresh-route-probes",
            "global_market_healthy": True,
            "probe": {
                "outcome": "unavailable",
                "consecutive": 2,
                "slot": 101,
                "first_observed_at": (now - timedelta(seconds=2)).isoformat(),
                "observed_at": (now - timedelta(seconds=1)).isoformat(),
            },
        }
    return item


@pytest.mark.parametrize(
    ("disposition", "expected_status", "expected_return"),
    [
        ("unknown", LearningEvidenceStatus.UNAVAILABLE, None),
        ("write_off", LearningEvidenceStatus.COMPLETE, -1.0),
    ],
)
def test_reset_finalizes_execution_evidence_without_fabricating_unknown_returns(
    tmp_path: Path,
    disposition: str,
    expected_status: LearningEvidenceStatus,
    expected_return: float | None,
) -> None:
    database = Database(tmp_path / f"execution-{disposition}.sqlite3")
    now = datetime.now(UTC)
    database.initialize_portfolio("season-one", 1_000, "SOL")
    database.save_learning_evidence_episode(execution_episode(now))
    summary = {
        "ending_equity_minor": 900,
        "last_known_ending_equity_minor": 900,
        "peak_equity_minor": 1_000,
        "realized_pnl_minor": 0,
        "net_pnl_minor": -100,
        "total_fees_minor": 2,
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "break_even": 0,
        "ending_drawdown_fraction": 0.1,
        "open_positions": 1,
        "meaningful_activity": True,
    }

    database.reset_paper_state(
        summary,
        unresolved_positions=[unresolved_episode_inventory(now, disposition=disposition)],
    )

    episode = database.list_learning_evidence_episodes()[0]
    assert episode.status == expected_status
    assert episode.realized_return_fraction == expected_return
    assert episode.completed_at is not None
    assert episode.entry_fill_id == "entry-fill"
    database.close()


def test_save_order_links_policy_episode_atomically(tmp_path: Path) -> None:
    database = Database(tmp_path / "policy-order-link.sqlite3")
    now = datetime.now(UTC)
    episode = execution_episode(now, episode_id="policy-one").model_copy(
        update={
            "lane": LearningEvidenceLane.POLICY,
            "decision_id": "decision-one",
            "entry_fill_id": None,
        }
    )
    database.save_learning_evidence_episode(episode)
    order = PaperOrder(
        order_id="order-one",
        decision_id="decision-one",
        mint=episode.mint,
        symbol=episode.symbol,
        side=Side.BUY,
        requested_sol_lamports=100,
        created_at=now,
        fill_after=now,
    )

    database.save_order(order)

    linked = database.list_learning_evidence_episodes()[0]
    assert linked.order_id == order.order_id
    database.close()


def test_history_pruning_keeps_non_trade_evidence(tmp_path: Path) -> None:
    database = Database(tmp_path / "arcade.sqlite3")
    now = datetime.now(UTC)
    for event_id, kind, received_at in (
        ("old-trade", EventKind.TRADE, now - timedelta(days=2)),
        ("old-create", EventKind.CREATE, now - timedelta(days=2)),
        ("new-trade", EventKind.TRADE, now),
    ):
        database.append_event(
            MarketEvent(
                event_id=event_id,
                source="test",
                kind=kind,
                mint="Mint111111111111111111111111111111111111111",
                received_at=received_at,
            )
        )
    for value in (1, 2, 3):
        database.record_equity(value, value)
    removed = database.prune_history(now - timedelta(hours=24), max_equity_points=1)
    assert removed == {
        "raw_trades": 1,
        "non_entry_decisions": 0,
        "equity_points": 2,
    }
    assert {item.event_id for item in database.recent_events()} == {"old-create", "new-trade"}
    assert len(database.equity_history()) == 1
    database.close()


def test_history_pruning_is_bounded_per_maintenance_pass(tmp_path: Path) -> None:
    database = Database(tmp_path / "bounded-prune.sqlite3")
    now = datetime.now(UTC)
    for index in range(5):
        database.append_event(
            MarketEvent(
                event_id=f"old-trade-{index}",
                source="test",
                kind=EventKind.TRADE,
                mint="Mint111111111111111111111111111111111111111",
                received_at=now - timedelta(days=2, seconds=index),
            )
        )

    removed = database.prune_history(
        now - timedelta(hours=24),
        max_rows_per_category=2,
    )

    assert removed["raw_trades"] == 2
    assert len(database.recent_events()) == 3
    database.close()


def test_storage_maintenance_never_prunes_season_scorecards(tmp_path: Path) -> None:
    database = Database(tmp_path / "season-retention.sqlite3")
    database.initialize_portfolio("season-one", 1_000_000_000, "SOL")
    database.reset_paper_state(
        {
            "ending_equity_minor": 980_000_000,
            "last_known_ending_equity_minor": 980_000_000,
            "peak_equity_minor": 1_050_000_000,
            "realized_pnl_minor": -20_000_000,
            "net_pnl_minor": -20_000_000,
            "total_fees_minor": 1_000_000,
            "closed_trades": 3,
            "wins": 1,
            "losses": 2,
            "break_even": 0,
            "ending_drawdown_fraction": 0.066,
            "open_positions": 0,
            "meaningful_activity": True,
        }
    )
    database.initialize_portfolio("season-two", 1_000_000_000, "SOL")
    now = datetime.now(UTC)
    database.append_event(
        MarketEvent(
            event_id="old-season-trade",
            source="test",
            kind=EventKind.TRADE,
            mint="Mint111111111111111111111111111111111111111",
            received_at=now - timedelta(days=2),
        )
    )

    database.prune_history(now - timedelta(hours=24), max_equity_points=1)
    database.enforce_storage_budget(1, preserve_recent_events=0)

    assert [(row["season_number"], row["status"]) for row in database.list_paper_seasons()] == [
        (1, "completed"),
        (2, "current"),
    ]
    database.close()


def test_storage_budget_stops_between_committed_chunks_for_upgrade(tmp_path: Path) -> None:
    database = Database(tmp_path / "cooperative-storage-stop.sqlite3")
    now = datetime.now(UTC)
    for index in range(20):
        database.append_event(
            MarketEvent(
                event_id=f"upgrade-stop-{index}",
                source="test",
                kind=EventKind.TRADE,
                mint="Mint111111111111111111111111111111111111111",
                received_at=now - timedelta(days=2, seconds=index),
            )
        )

    result = database.enforce_storage_budget(
        1,
        preserve_recent_events=0,
        stop_requested=lambda: True,
    )

    assert result["raw_trades"] == 0
    assert len(database.recent_events()) == 20
    database.close()


def test_event_batches_are_atomic_and_deduplicated(tmp_path: Path) -> None:
    database = Database(tmp_path / "batch.sqlite3")
    now = datetime.now(UTC)
    events = [
        MarketEvent(
            event_id=f"event-{index}",
            source="test",
            kind=EventKind.CREATE,
            mint=f"Mint{index}",
            received_at=now,
        )
        for index in range(3)
    ]
    assert database.append_events([*events, events[0]]) == {
        "event-0",
        "event-1",
        "event-2",
    }
    assert database.append_events(events) == set()
    assert len(database.recent_events()) == 3
    database.close()


def test_operational_incidents_deduplicate_resolve_and_persist(tmp_path: Path) -> None:
    path = tmp_path / "incidents.sqlite3"
    database = Database(path)
    first = database.record_incident(
        scope="stream",
        severity="warning",
        title="Stream reconnected",
        detail="first",
    )
    repeated = database.record_incident(
        scope="stream",
        severity="warning",
        title="Stream reconnected",
        detail="second",
    )
    assert repeated.incident_id == first.incident_id
    assert repeated.occurrences == 2
    assert database.resolve_incidents("stream") == 1
    database.close()

    reopened = Database(path)
    saved = reopened.list_incidents()
    assert len(saved) == 1
    assert saved[0].resolved_at is not None
    assert saved[0].occurrences == 2
    reopened.close()


def test_transient_incidents_are_resolved_immediately_and_coalesced(tmp_path: Path) -> None:
    database = Database(tmp_path / "transient-incidents.sqlite3")
    first_seen = datetime(2026, 1, 1, tzinfo=UTC)
    first = database.record_transient_incident(
        scope="stream",
        severity="info",
        title="Stream recovered automatically",
        detail="first episode",
        now=first_seen,
    )
    repeated = database.record_transient_incident(
        scope="stream",
        severity="info",
        title="Stream recovered automatically",
        detail="second episode",
        now=first_seen + timedelta(minutes=20),
    )

    assert repeated.incident_id == first.incident_id
    assert repeated.occurrences == 2
    assert repeated.resolved_at == first_seen + timedelta(minutes=20)
    assert database.list_incidents() == [repeated]

    later = database.record_transient_incident(
        scope="stream",
        severity="info",
        title="Stream recovered automatically",
        detail="separate episode",
        now=first_seen + timedelta(hours=2),
    )
    assert later.incident_id != first.incident_id
    assert len(database.list_incidents()) == 2
    database.close()


def test_compact_equity_keeps_hourly_history_when_raw_points_are_pruned(tmp_path: Path) -> None:
    database = Database(tmp_path / "equity.sqlite3")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(3):
        database.record_equity(
            1_000 + index,
            900 + index,
            recorded_at=base + timedelta(hours=index),
        )
    database.prune_history(base + timedelta(days=1), max_equity_points=1)
    compact = database.compact_equity_history(recent_limit=1, rollup_limit=10)
    assert len(compact) >= 3
    assert compact[-1]["equity_lamports"] == 1_002
    database.close()


def test_v5_migration_backfills_existing_equity_into_hourly_rollups(tmp_path: Path) -> None:
    path = tmp_path / "rollup-upgrade.sqlite3"
    database = Database(path)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    database.record_equity(1_000, 900, recorded_at=base)
    database.record_equity(1_100, 950, recorded_at=base + timedelta(minutes=30))
    database._conn.execute("DELETE FROM equity_rollups")  # noqa: SLF001
    database._conn.execute("PRAGMA user_version=4")  # noqa: SLF001
    database._conn.commit()  # noqa: SLF001
    database.close()

    upgraded = Database(path)
    upgraded.prune_history(base + timedelta(days=1), max_equity_points=1)
    compact = upgraded.compact_equity_history(recent_limit=1, rollup_limit=10)
    assert compact[0]["equity_lamports"] == 1_100
    assert (  # noqa: SLF001
        upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    )
    upgraded.close()
