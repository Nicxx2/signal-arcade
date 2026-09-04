from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.features import TokenState
from signal_arcade.intelligence.learning import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    LEARNER_VERSION_PREFIX,
    LEARNING_EVIDENCE_SCHEMA_VERSION,
    MANIPULATION_FEATURE_NAMES,
    SIZING_FEATURE_NAMES,
    LearningEngine,
    _challenger_cohort_key,
    _predict_skill_artifact,
)
from signal_arcade.models import (
    ChallengerSkill,
    ChallengerSkillArtifact,
    ChallengerSkillState,
    CoachCondition,
    CoachExperimentKind,
    CoachExperimentState,
    CoachHypothesis,
    DataValue,
    Decision,
    DecisionAction,
    DecisionScore,
    FeatureSnapshot,
    IntegrityAssessment,
    LearningCheckpoint,
    LearningEvidenceEpisode,
    LearningEvidenceLane,
    LearningEvidenceStatus,
    LearningMode,
    LearningModel,
    LearningObservation,
    LearningObservationStatus,
    MarketIntegrityState,
    RiskMode,
    SizingAssessment,
    StatisticalModelFamily,
)
from signal_arcade.paper.curve_math import quote_buy, quote_sell
from signal_arcade.strategy import BASELINE_VERSION, PREVIOUS_BASELINE_VERSION


def make_decision(now: datetime, mint: str, opportunity: float = 0.8) -> Decision:
    values = {
        "age_seconds": data(now, 30),
        "trade_count_5m": data(now, 20),
        "trade_count_1m": data(now, 12),
        "unique_wallets_5m": data(now, 10),
        "buy_ratio_5m": data(now, 0.7),
        "wallet_volume_hhi": data(now, 0.12),
        "repeated_amount_ratio": data(now, 0.1),
        "same_slot_ratio": data(now, 0.1),
        "curve_progress": data(now, 0.4),
        "momentum_1m": data(now, 0.2),
        "drawdown_5m": data(now, 0.05),
        "virtual_quote_reserve_sol": data(now, 30),
        "single_trade_wallet_ratio": data(now, 0.8),
        "round_trip_wallet_ratio": data(now, 0.1),
        "round_trip_volume_ratio": data(now, 0.15),
        "net_quote_flow_ratio": data(now, 0.6),
        "side_alternation_ratio": data(now, 0.4),
        "quantized_amount_repeat_ratio": data(now, 0.2),
        "slot_concentration_hhi": data(now, 0.1),
        "price_direction_consistency": data(now, 0.7),
        "microtrade_count_ratio": data(now, 0.1),
        "meaningful_volume_ratio": data(now, 0.9),
        "meaningful_wallet_ratio": data(now, 0.9),
        "median_trade_quote_sol": data(now, 0.03),
        "price_path_efficiency": data(now, 0.65),
        "rapid_price_reversal_ratio": data(now, 0.2),
        "trade_density_5m": data(now, 0.05),
    }
    snapshot = FeatureSnapshot(
        mint=mint,
        symbol="LEARN",
        name="Learning token",
        venue="pump_curve",
        computed_at=now,
        values=values,
        data_confidence=0.9,
    )
    return Decision(
        decision_id="decision-" + mint,
        mint=mint,
        symbol="LEARN",
        created_at=now,
        action=DecisionAction.ENTER,
        risk_mode=RiskMode.BALANCED,
        score=DecisionScore(
            opportunity=opportunity,
            danger=0.1,
            execution=0.9,
            confidence=0.9,
            net_edge_index=0.08,
            composite=80,
        ),
        reasons=["eligible"],
        blockers=[],
        feature_snapshot=snapshot,
        planned_order_size_sol=0.025,
        model_version=BASELINE_VERSION,
        season_id="test-season",
    )


def data(now: datetime, value: float) -> DataValue:
    return DataValue(
        value=value,
        unit="test",
        as_of=now,
        sources=["test"],
        freshness_seconds=0,
        quality=1,
    )


def make_state(mint: str) -> TokenState:
    return TokenState(
        mint=mint,
        symbol="LEARN",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
        fee_bps=125,
    )


def policy_episode_for(learner: LearningEngine, mint: str) -> LearningEvidenceEpisode:
    return next(
        episode
        for episode in learner.evidence_episodes.values()
        if episode.mint == mint and episode.lane == LearningEvidenceLane.POLICY
    )


def resolve_policy_primary(
    learner: LearningEngine,
    mint: str,
    observed_at: datetime,
    outcome: float | None,
) -> LearningEvidenceEpisode:
    episode = policy_episode_for(learner, mint)
    episode.checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=observed_at,
        net_return=outcome,
        exit_value_lamports=None if outcome is None else max(0, int((1 + outcome) * 1_000_000)),
        missing_reason="route_unavailable" if outcome is None else None,
    )
    learner.database.save_learning_evidence_episode(episode)
    return episode


def resolve_forward_primary(
    learner: LearningEngine,
    mint: str,
    observed_at: datetime,
    outcome: float | None,
    *,
    missing_reason: str | None = None,
) -> None:
    """Resolve the discovery view and authoritative policy journal for one test entry."""

    checkpoint = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=observed_at,
        net_return=outcome,
        exit_value_lamports=None if outcome is None else max(0, int((1 + outcome) * 1_000_000)),
        missing_reason=missing_reason,
    )
    observation = learner.observations[mint]
    observation.checkpoints["300"] = checkpoint.model_copy(deep=True)
    learner.database.save_learning_observation(observation)
    episode = policy_episode_for(learner, mint)
    episode.checkpoints["300"] = checkpoint.model_copy(deep=True)
    learner.database.save_learning_evidence_episode(episode)


def qualified_model(version: str, prediction: float, outcomes_seen: int) -> LearningModel:
    return LearningModel(
        version=f"{LEARNER_VERSION_PREFIX}{version}",
        outcomes_seen=outcomes_seen,
        risk_mode=RiskMode.BALANCED,
        sample_count=80,
        resolved_count=80,
        outcome_availability_fraction=1.0,
        training_count=50,
        validation_count=26,
        embargoed_count=4,
        feature_names=list(FEATURE_NAMES),
        means=[0.0] * len(FEATURE_NAMES),
        scales=[1.0] * len(FEATURE_NAMES),
        coefficients=[prediction, *([0.0] * len(FEATURE_NAMES))],
        validation_rmse=0.05,
        naive_rmse=0.2,
        learner_correlation=0.5,
        baseline_correlation=0.1,
        learner_top_mean_return=0.2,
        baseline_top_mean_return=0.1,
        overall_mean_return=0.05,
        validation_in_distribution_fraction=1.0,
        policy_validation_count=20,
        policy_observed_count=20,
        policy_outcome_availability_fraction=1.0,
        policy_supported_count=15,
        policy_veto_count=5,
        policy_winner_veto_count=0,
        policy_winner_veto_fraction=0.0,
        policy_mean_uplift=0.05,
        policy_uplift_lower_bound=0.01,
        qualification_evidence_schema_version=LEARNING_EVIDENCE_SCHEMA_VERSION,
        qualified=True,
    )


def test_unqualified_skill_candidate_is_collecting_proof_not_suspended(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "candidate-status-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        configuration,
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    artifact = ChallengerSkillArtifact(
        version="challenger-skill-v1-manipulation-unqualified",
        skill=ChallengerSkill.MANIPULATION,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        outcomes_seen=80,
        sample_count=80,
        training_count=50,
        validation_count=26,
        embargoed_count=4,
        qualified=False,
        qualification_reasons=["manipulation_proof_gates_not_met"],
    )

    learner._register_skill_artifact(artifact, cohort_key)  # noqa: SLF001

    state = learner.skill_states[(cohort_key, ChallengerSkill.MANIPULATION)]
    assert state.champion_version is None
    assert state.suspended_version is None
    status = next(
        item
        for item in learner.status(demo_mode=False)["skills"]
        if item["skill"] == ChallengerSkill.MANIPULATION.value
    )
    assert status["state"] == "collecting_proof"
    assert status["health"]["state"] == "inactive"
    restarted = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    restarted_status = next(
        item
        for item in restarted.skill_statuses()
        if item["skill"] == ChallengerSkill.MANIPULATION.value
    )
    assert restarted_status["state"] == "collecting_proof"
    assert restarted_status["health"]["state"] == "inactive"
    database.close()


def test_deferred_family_selection_requires_nonlinear_complexity_to_be_earned(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "family-config")
    monkeypatch.setattr(learner, "_load_nonlinear_artifact", lambda _artifact: object())
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        "family-config",
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    now = datetime.now(UTC)

    def candidate(
        version: str, family: StatisticalModelFamily, rmse: float
    ) -> ChallengerSkillArtifact:
        return ChallengerSkillArtifact(
            version=version,
            created_at=now,
            skill=ChallengerSkill.ENTRY,
            model_family=family,
            risk_mode=RiskMode.BALANCED,
            configuration_fingerprint="family-config",
            baseline_version=BASELINE_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            metrics={"validation_rmse": rmse, "policy_uplift_lower": 0.02},
            qualified=True,
        )

    linear = candidate("linear-family", StatisticalModelFamily.LINEAR, 0.10)
    marginal = candidate("marginal-xgb", StatisticalModelFamily.XGBOOST, 0.099)
    state = ChallengerSkillState(
        cohort_key=cohort_key,
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="family-config",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        pending_versions=[linear.version, marginal.version],
    )
    learner.skill_artifacts.update({linear.version: linear, marginal.version: marginal})

    learner._start_next_skill_tournament(state)  # noqa: SLF001

    assert state.champion_version == linear.version
    assert state.testing_version == marginal.version

    clearly_better = candidate("clear-xgb", StatisticalModelFamily.XGBOOST, 0.07)
    fresh_state = state.model_copy(
        update={
            "champion_version": None,
            "testing_version": None,
            "pending_versions": [linear.version, clearly_better.version],
            "champion_journey": [],
        }
    )
    learner.skill_artifacts[clearly_better.version] = clearly_better

    learner._start_next_skill_tournament(fresh_state)  # noqa: SLF001

    assert fresh_state.champion_version == clearly_better.version
    assert fresh_state.testing_version == linear.version

    perfect_linear = candidate("perfect-linear", StatisticalModelFamily.LINEAR, 0.0)
    perfect_nonlinear = candidate("perfect-xgb", StatisticalModelFamily.XGBOOST, 0.0)
    perfect_state = state.model_copy(
        update={
            "champion_version": None,
            "testing_version": None,
            "pending_versions": [perfect_linear.version, perfect_nonlinear.version],
            "champion_journey": [],
        }
    )
    learner.skill_artifacts.update(
        {
            perfect_linear.version: perfect_linear,
            perfect_nonlinear.version: perfect_nonlinear,
        }
    )

    learner._start_next_skill_tournament(perfect_state)  # noqa: SLF001

    assert perfect_state.champion_version == perfect_linear.version
    assert perfect_state.testing_version == perfect_nonlinear.version
    database.close()


def test_unavailable_champion_does_not_discard_available_contender(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "unavailable-champion-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        configuration,
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    champion = ChallengerSkillArtifact(
        version="missing-xgb-champion",
        skill=ChallengerSkill.ENTRY,
        model_family=StatisticalModelFamily.XGBOOST,
        payload_format="json",
        payload_digest="0" * 64,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        qualified=True,
    )
    contender = champion.model_copy(
        update={
            "version": "available-linear-contender",
            "model_family": StatisticalModelFamily.LINEAR,
            "payload_format": "inline",
            "payload_digest": "",
        }
    )
    state = ChallengerSkillState(
        cohort_key=cohort_key,
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        champion_version=champion.version,
        testing_version=contender.version,
    )
    learner.skill_artifacts.update({champion.version: champion, contender.version: contender})
    learner.skill_states[(cohort_key, ChallengerSkill.ENTRY)] = state

    learner._advance_entry_tournaments()  # noqa: SLF001

    assert state.champion_version == champion.version
    assert state.suspended_version == champion.version
    assert state.testing_version is None
    assert state.pending_versions == [contender.version]
    assert contender.version not in state.rejected_versions
    database.close()


def test_learning_uses_live_forward_costed_outcomes_only(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    state = make_state("mint-live")

    assert (
        learner.register(make_decision(now, "mint-demo"), make_state("mint-demo"), live=False)
        is False
    )
    live_decision = make_decision(now, "mint-live").model_copy(
        update={
            "season_id": "season-balanced-default",
            "season_profile_fingerprint": "a" * 64,
            "configuration_fingerprint": "balanced-learning-lineage",
        }
    )
    assert (
        learner.register(
            live_decision,
            state,
            live=True,
            evaluation_actionable=True,
        )
        is True
    )
    assert learner.register(make_decision(now, "mint-live"), state, live=True) is False
    assert learner.pending_mints == {"mint-live"}
    assert learner.has_pending_mint("mint-live") is True
    assert learner.has_pending_mint("not-observed") is False
    assert learner.observations["mint-live"].baseline_actionable is True
    assert learner.observations["mint-live"].evaluation_actionable is False
    assert learner.observations["mint-live"].season_id == "season-balanced-default"
    assert learner.observations["mint-live"].season_profile_fingerprint == "a" * 64
    persisted = {item.mint: item for item in database.list_learning_observations()}
    assert persisted["mint-live"].season_profile_fingerprint == "a" * 64

    improved = make_state("mint-live")
    improved.virtual_quote_reserves = 45_000_000_000
    assert learner.observe_market(improved, now + timedelta(seconds=60), live=True) == 2
    first = learner.observations["mint-live"].checkpoints["60"]
    assert first.net_return is not None
    assert first.exit_value_lamports is not None
    entry = quote_buy(
        virtual_token_reserves=state.virtual_token_reserves,
        virtual_sol_reserves=state.virtual_quote_reserves,
        real_token_reserves=state.real_token_reserves,
        wallet_trade_budget_lamports=25_000_000,
        fee_bps=125,
        network_fee_lamports=15_000,
    )
    exit_quote = quote_sell(
        virtual_token_reserves=improved.virtual_token_reserves,
        virtual_sol_reserves=improved.virtual_quote_reserves,
        token_units=entry.token_units,
        fee_bps=125,
        network_fee_lamports=15_000,
    )
    assert first.net_return == pytest.approx(
        (exit_quote.wallet_sol_lamports - entry.wallet_sol_lamports) / entry.wallet_sol_lamports
    )
    assert learner.observe_market(improved, now + timedelta(seconds=300), live=True) == 2
    assert learner.observe_market(improved, now + timedelta(seconds=600), live=True) == 2
    assert learner.observe_market(improved, now + timedelta(seconds=900), live=True) == 2
    assert learner.observe_market(improved, now + timedelta(seconds=1_200), live=True) == 2
    observation = learner.observations["mint-live"]
    assert observation.status == LearningObservationStatus.COMPLETE
    assert learner.has_pending_mint("mint-live") is False
    assert observation.checkpoints["300"].net_return is not None
    assert database.list_learning_observations()[0].status == LearningObservationStatus.COMPLETE
    database.reset_paper_state()
    assert len(database.list_learning_observations()) == 1
    assert len(database.list_learning_evidence_episodes()) == 1
    database.close()


def test_clock_sampler_uses_only_fresh_cached_route_evidence(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    state = make_state("clock-route")
    assert learner.register(make_decision(now, state.mint), state, live=True)

    state.last_reserve_at = now + timedelta(seconds=300)
    state.last_event_at = state.last_reserve_at
    state.last_event_id = "trade-at-checkpoint"
    state.reserve_source = "solana:logs"
    assert (
        learner.sample_due_checkpoints(
            {state.mint: state},
            now + timedelta(seconds=300),
            live=True,
        )
        == 2
    )
    checkpoint = learner.observations[state.mint].checkpoints["300"]
    assert checkpoint.net_return is not None
    assert checkpoint.route_event_id == "trade-at-checkpoint"
    assert checkpoint.route_source == "solana:logs"
    assert checkpoint.reserve_age_seconds == 0
    database.close()


def test_clock_sampler_never_prices_stale_routes_and_records_exact_reason(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    states: dict[str, TokenState] = {}
    for mint in ("stale-a", "fresh-b"):
        state = make_state(mint)
        assert learner.register(make_decision(now, mint), state, live=True)
        state.last_reserve_at = now if mint == "stale-a" else now + timedelta(seconds=300)
        state.last_event_at = state.last_reserve_at
        states[mint] = state

    sampled = learner.sample_due_checkpoints(
        states,
        now + timedelta(seconds=300),
        live=True,
        max_observations=1,
    )
    assert sampled == 2
    assert "300" not in learner.observations["stale-a"].checkpoints
    # An old stale item cannot starve a fresh due route when work is bounded.
    assert learner.observations["fresh-b"].checkpoints["300"].net_return is not None

    assert (
        learner.expire_checkpoints(
            now + timedelta(seconds=391),
            states=states,
        )
        >= 2
    )
    stale = learner.observations["stale-a"].checkpoints["300"]
    assert stale.net_return is None
    assert stale.missing_reason == "stale_cached_route"
    assert learner.status(demo_mode=False)["unavailable_outcome_reasons"]["stale_cached_route"] == 1
    database.close()


def test_candidate_replaces_champion_only_on_common_forward_evidence(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "baseline-v1.2-tournament-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    champion = qualified_model("champion", 0.20, 80).model_copy(
        update={
            "created_at": now,
            "configuration_fingerprint": configuration,
        }
    )
    candidate = qualified_model("candidate", -0.20, 90).model_copy(
        update={
            "created_at": now + timedelta(seconds=1),
            "configuration_fingerprint": configuration,
        }
    )
    learner._publish_entry_artifact(  # noqa: SLF001 - exercise tournament boundary directly
        champion,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        candidate,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    state = next(iter(learner.skill_states.values()))
    original_champion = state.champion_version
    contender = state.testing_version
    assert original_champion is not None
    assert contender is not None
    assert original_champion != contender
    assert [event.kind for event in state.champion_journey] == ["first_champion"]
    assert state.champion_journey[0].champion_version == original_champion
    learner.entry_outcome_availability = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "qualified": True
    }
    learner.set_mode(LearningMode.ACTIVE)
    assert learner.active_skill_versions["entry"] == original_champion

    for index in range(30):
        observed_at = now + timedelta(minutes=10 + index)
        mint = f"tournament-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        observation = learner.observations[mint]
        assert set(observation.challenger_evaluations) == {original_champion, contender}
        assert set(policy_episode_for(learner, mint).challenger_evaluations) == {
            original_champion,
            contender,
        }
        resolve_forward_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            -0.10,
        )
        learner._advance_entry_tournaments()  # noqa: SLF001
        if index < 29:
            assert state.champion_version == original_champion

    assert state.champion_version == contender
    assert state.testing_version is None
    assert state.active_version == contender
    assert learner.active_skill_versions["entry"] == contender
    assert state.last_tournament["result"] == "promoted"
    assert state.last_tournament["common_usable_count"] == 30
    assert [event.kind for event in state.champion_journey] == ["first_champion", "promoted"]
    promotion = state.champion_journey[-1]
    assert promotion.previous_champion_version == original_champion
    assert promotion.champion_version == contender
    assert (
        next(item for item in learner.skill_statuses() if item["skill"] == "entry")[
            "champion_generation"
        ]
        == 2
    )
    assert promotion.common_usable_count == 30
    learner._advance_entry_tournaments()  # noqa: SLF001 - a settled battle is idempotent
    assert [event.kind for event in state.champion_journey] == ["first_champion", "promoted"]
    stale_state = state.model_copy(
        update={
            "cohort_key": "stale-configuration-cohort",
            "configuration_fingerprint": "stale-configuration",
            "champion_version": "missing-old-champion",
            "testing_version": "missing-old-candidate",
            "suspended_version": None,
        }
    )
    learner.skill_states[(stale_state.cohort_key, ChallengerSkill.ENTRY)] = stale_state
    learner._advance_entry_tournaments()  # noqa: SLF001
    assert stale_state.testing_version == "missing-old-candidate"
    assert stale_state.suspended_version is None
    restarted = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    restarted_state = next(iter(restarted.skill_states.values()))
    assert restarted_state.champion_version == contender
    assert restarted.active_skill_versions["entry"] == contender
    assert [event.kind for event in restarted_state.champion_journey] == [
        "first_champion",
        "promoted",
    ]
    assert [event["kind"] for event in restarted.status(demo_mode=False)["champion_journey"]] == [
        "promoted",
        "first_champion",
    ]
    assert restarted.status(demo_mode=False)["challenger_common_forward_minimum"] == 30
    assert restarted.status(demo_mode=False)["challenger_minimum_availability"] == 0.70
    database.close()


def test_champion_journey_is_durable_idempotent_and_recent_view_is_cohort_isolated(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "champion-history-current"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    champion = qualified_model("journey-champion", 0.2, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001 - exercise durable event boundary
        champion,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    state = next(iter(learner.skill_states.values()))
    original_champion = state.champion_version
    assert original_champion is not None
    for index in range(14):
        learner._append_champion_event(  # noqa: SLF001
            state,
            kind="defended",
            candidate_version=f"contender-{index}",
            previous_champion_version=state.champion_version,
            champion_version=state.champion_version or "missing",
            common_observed_count=30,
            common_usable_count=30,
            availability_fraction=1.0,
            mean_uplift=-0.01,
            uplift_lower_bound=-0.02,
            occurred_at=now + timedelta(minutes=index + 1),
        )
    assert len(state.champion_journey) == 15
    retained_ids = [event.event_id for event in state.champion_journey]
    learner._append_champion_event(  # noqa: SLF001 - duplicate must remain a no-op
        state,
        kind="defended",
        candidate_version="contender-13",
        previous_champion_version=state.champion_version,
        champion_version=state.champion_version or "missing",
        common_observed_count=30,
        common_usable_count=30,
        availability_fraction=1.0,
    )
    assert [event.event_id for event in state.champion_journey] == retained_ids
    database.save_challenger_skill_state(state)
    recent_view = learner.champion_journey()
    assert all(event["champion_codename"] for event in recent_view)
    assert all(event["candidate_codename"] for event in recent_view)
    assert {event["champion_generation"] for event in recent_view} == {1}
    assert all(event["resolution"] for event in recent_view)

    first_page = learner.champion_journey_page(limit=5)
    assert first_page["total"] == 15
    assert len(first_page["events"]) == 5
    assert first_page["next_cursor"] == first_page["events"][-1]["event_id"]
    second_page = learner.champion_journey_page(
        limit=5,
        cursor=first_page["next_cursor"],
    )
    assert len(second_page["events"]) == 5
    assert {event["event_id"] for event in first_page["events"]}.isdisjoint(
        event["event_id"] for event in second_page["events"]
    )
    with pytest.raises(ValueError, match="no longer in this learning cohort"):
        learner.champion_journey_page(limit=5, cursor="unknown-event")

    record = learner.champion_records()[0]
    assert record["champion_version"] == original_champion
    assert record["champion_generation"] == 1
    assert record["retained_count"] == 14
    assert record["inconclusive_count"] == 0
    assert record["recorded_battle_count"] == 14
    assert record["influence_state"] == "shadow"
    assert record["history_complete"] is True

    learner.current_risk_mode = RiskMode.SAFE
    assert learner.champion_journey() == []
    learner.current_risk_mode = RiskMode.BALANCED
    restarted = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    restarted_state = next(iter(restarted.skill_states.values()))
    restarted_state.active_version = original_champion
    restarted_state.suspended_version = original_champion
    suspended_record = restarted.champion_records()[0]
    assert suspended_record["influence_state"] == "suspended"
    assert suspended_record["active"] is False
    assert [event.event_id for event in restarted_state.champion_journey] == retained_ids
    assert len(restarted_state.champion_journey) == 15
    assert restarted.champion_journey() == recent_view
    database.close()


def test_nonlinear_entry_status_is_exact_cohort_eligibility_not_promotion_progress(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "nonlinear-status-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    stale_linear = ChallengerSkillArtifact(
        version="challenger-skill-v2-entry-stale-linear-status",
        skill=ChallengerSkill.ENTRY,
        model_family=StatisticalModelFamily.LINEAR,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=PREVIOUS_BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        training_count=999,
        qualified=True,
    )
    learner.skill_artifacts[stale_linear.version] = stale_linear
    assert learner.nonlinear_entry_status() == {
        "state": "collecting",
        "eligible_training_count": 0,
        "minimum_training_samples": 250,
        "required_linear_improvement_fraction": 0.02,
        "latest_artifact": None,
        "entry_only": True,
    }

    linear = ChallengerSkillArtifact(
        version="challenger-skill-v2-entry-linear-status",
        skill=ChallengerSkill.ENTRY,
        model_family=StatisticalModelFamily.LINEAR,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        training_count=250,
        qualified=True,
    )
    learner.skill_artifacts[linear.version] = linear
    assert learner.nonlinear_entry_status()["state"] == "eligible"

    version = "challenger-skill-v2-entry-xgboost-status"
    nonlinear = ChallengerSkillArtifact(
        version=version,
        skill=ChallengerSkill.ENTRY,
        model_family=StatisticalModelFamily.XGBOOST,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        training_count=250,
        qualified=False,
    )
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        configuration,
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    learner.skill_artifacts[version] = nonlinear
    learner.skill_states[(cohort_key, ChallengerSkill.ENTRY)] = ChallengerSkillState(
        cohort_key=cohort_key,
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        latest_candidate_version=version,
    )
    status = learner.nonlinear_entry_status()
    assert status["state"] == "proof_not_met"
    assert status["latest_artifact"]["model_family"] == "xgboost"

    newer_linear = linear.model_copy(
        update={
            "version": "challenger-skill-v2-entry-new-linear-status",
            "created_at": nonlinear.created_at + timedelta(seconds=1),
            "training_count": 275,
        }
    )
    learner.skill_artifacts[newer_linear.version] = newer_linear
    refreshed_status = learner.nonlinear_entry_status()
    assert refreshed_status["state"] == "eligible"
    assert refreshed_status["eligible_training_count"] == 275

    learner.skill_states[(cohort_key, ChallengerSkill.ENTRY)].champion_version = version
    assert learner.nonlinear_entry_status()["state"] == "champion"
    learner.skill_states[(cohort_key, ChallengerSkill.ENTRY)].suspended_version = version
    assert learner.nonlinear_entry_status()["state"] == "suspended"
    database.close()


def test_champion_journey_records_a_real_common_forward_defence(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "champion-defence-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    champion = qualified_model("defence-champion", 0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    candidate = qualified_model("defence-candidate", -0.20, 90).model_copy(
        update={
            "created_at": now + timedelta(seconds=1),
            "configuration_fingerprint": configuration,
        }
    )
    for model in (champion, candidate):
        learner._publish_entry_artifact(  # noqa: SLF001 - exercise real battle result
            model,
            baseline_version=BASELINE_VERSION,
            evidence_started_at=now - timedelta(hours=1),
            evidence_ended_at=model.created_at,
        )
    state = next(iter(learner.skill_states.values()))
    original_champion = state.champion_version
    contender = state.testing_version
    assert original_champion is not None
    assert contender is not None

    for index in range(30):
        observed_at = now + timedelta(minutes=10 + index)
        mint = f"defence-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        resolve_forward_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            0.10,
        )
        learner._advance_entry_tournaments()  # noqa: SLF001

    assert state.champion_version == original_champion
    assert state.testing_version is None
    assert state.last_tournament["result"] == "rejected"
    defence = state.champion_journey[-1]
    assert defence.kind == "defended"
    assert defence.candidate_version == contender
    assert defence.champion_version == original_champion
    assert defence.common_usable_count == 30
    database.close()


def test_champion_journey_closes_a_max_length_tie_as_inconclusive(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "champion-inconclusive-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    champion = qualified_model("tie-champion", -0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    candidate = qualified_model("tie-candidate", 0.20, 90).model_copy(
        update={
            "created_at": now + timedelta(seconds=1),
            "configuration_fingerprint": configuration,
        }
    )
    for model in (champion, candidate):
        learner._publish_entry_artifact(  # noqa: SLF001
            model,
            baseline_version=BASELINE_VERSION,
            evidence_started_at=now - timedelta(hours=1),
            evidence_ended_at=model.created_at,
        )
    state = next(iter(learner.skill_states.values()))
    original_champion = state.champion_version

    for index in range(120):
        observed_at = now + timedelta(minutes=10 + index)
        mint = f"inconclusive-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        outcome = -0.10 if index % 10 < 3 else 0.043
        resolve_forward_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            outcome,
        )
        learner._advance_entry_tournaments()  # noqa: SLF001

    assert state.champion_version == original_champion
    assert state.testing_version is None
    tie = state.champion_journey[-1]
    assert tie.kind == "inconclusive"
    assert tie.common_usable_count == 120
    assert tie.uplift_lower_bound is not None and tie.uplift_lower_bound <= 0
    database.close()


def test_champion_tournament_cannot_run_forever_on_poor_outcome_coverage(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "champion-low-coverage-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    champion = qualified_model("coverage-champion", -0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    candidate = qualified_model("coverage-candidate", 0.20, 90).model_copy(
        update={
            "created_at": now + timedelta(seconds=1),
            "configuration_fingerprint": configuration,
        }
    )
    for model in (champion, candidate):
        learner._publish_entry_artifact(  # noqa: SLF001
            model,
            baseline_version=BASELINE_VERSION,
            evidence_started_at=now - timedelta(hours=1),
            evidence_ended_at=model.created_at,
        )
    state = next(iter(learner.skill_states.values()))
    original_champion = state.champion_version

    # 53 unavailable plus 119 usable outcomes leaves coverage just below 70% after 172
    # resolved common-forward cases. The trial must stop safely instead of collecting forever.
    for index in range(172):
        observed_at = now + timedelta(minutes=10 + index)
        mint = f"low-coverage-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        resolve_forward_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            None if index < 53 else 0.043,
            missing_reason="route_unavailable" if index < 53 else None,
        )
        learner._advance_entry_tournaments()  # noqa: SLF001

    assert state.champion_version == original_champion
    assert state.testing_version is None
    assert state.last_tournament["result"] == "inconclusive"
    assert state.last_tournament["common_observed_count"] == 172
    assert state.last_tournament["common_usable_count"] == 119
    assert float(state.last_tournament["availability_fraction"]) < 0.70
    assert state.champion_journey[-1].kind == "inconclusive"
    database.close()


def test_retraining_interval_counts_only_new_outcomes_in_the_exact_cohort(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "cohort-a"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    model = qualified_model("cohort-interval", 0.2, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner.models.append(model)

    for cohort, count in (("cohort-b", 10), (configuration, 1)):
        for index in range(count):
            created_at = now + timedelta(
                minutes=10 + index + (20 if cohort == configuration else 0)
            )
            mint = f"{cohort}-{index}"
            decision = make_decision(created_at, mint).model_copy(
                update={
                    "model_version": BASELINE_VERSION,
                    "configuration_fingerprint": cohort,
                }
            )
            assert learner.register(decision, make_state(mint), live=True)
            observation = learner.observations[mint]
            observation.checkpoints["300"] = LearningCheckpoint(
                horizon_seconds=300,
                observed_at=created_at + timedelta(seconds=300),
                net_return=0.05,
                exit_value_lamports=1,
            )

    assert learner._new_outcomes_since_model(model) == 1  # noqa: SLF001
    assert learner.status(demo_mode=False)["outcomes_until_next_training"] == 9
    database.close()


def test_primary_resolution_queues_the_cohort_that_actually_changed(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    decision = make_decision(now, "delayed-cohort-a").model_copy(
        update={
            "model_version": BASELINE_VERSION,
            "configuration_fingerprint": "cohort-a",
        }
    )
    assert learner.register(decision, make_state(decision.mint), live=True)
    calls: list[tuple[RiskMode | None, str | None]] = []
    monkeypatch.setattr(
        learner,
        "request_retraining",
        lambda *, target_mode=None, target_configuration=None: calls.append(
            (target_mode, target_configuration)
        ),
    )

    assert (
        learner.observe_market(
            make_state(decision.mint),
            now + timedelta(seconds=300),
            live=True,
        )
        == 2
    )
    assert calls == [(RiskMode.BALANCED, "cohort-a")]
    database.close()


def test_learning_event_priority_only_backpressures_exact_horizon_windows(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    mint = "priority-window"
    assert learner.register(make_decision(now, mint), make_state(mint), live=True)

    assert learner.pending_event_priority(mint, now + timedelta(seconds=10)) == 1
    assert learner.pending_event_priority(mint, now + timedelta(seconds=45)) == 0
    assert learner.pending_event_priority("untracked", now) is None
    database.close()


def test_background_training_requests_coalesce_and_run_one_cohort(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    calls: list[tuple[RiskMode | None, str | None]] = []
    monkeypatch.setattr(
        learner,
        "_retrain_if_ready",
        lambda *, target_mode=None, target_configuration=None: calls.append(
            (target_mode, target_configuration)
        ),
    )
    learner.request_retraining(
        target_mode=RiskMode.BALANCED,
        target_configuration="same-cohort",
    )
    learner.request_retraining(
        target_mode=RiskMode.BALANCED,
        target_configuration="same-cohort",
    )

    assert learner.training_status()["queued"] == 1
    assert learner.run_next_training() is True
    assert calls == [(RiskMode.BALANCED, "same-cohort")]
    assert learner.training_status()["state"] == "idle"
    assert learner.training_status()["runs"] == 1
    database.close()


def test_training_request_arriving_during_active_fit_is_not_lost(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    calls: list[tuple[RiskMode | None, str | None]] = []

    def fit(*, target_mode=None, target_configuration=None):  # type: ignore[no-untyped-def]
        calls.append((target_mode, target_configuration))
        if len(calls) == 1:
            learner.request_retraining(
                target_mode=RiskMode.BALANCED,
                target_configuration="same-cohort",
            )

    monkeypatch.setattr(learner, "_retrain_if_ready", fit)
    learner.request_retraining(
        target_mode=RiskMode.BALANCED,
        target_configuration="same-cohort",
    )

    assert learner.run_next_training() is True
    assert learner.training_status()["queued"] == 1
    assert learner.run_next_training() is True
    assert calls == [
        (RiskMode.BALANCED, "same-cohort"),
        (RiskMode.BALANCED, "same-cohort"),
    ]
    assert learner.training_status()["state"] == "idle"
    database.close()


def test_manipulation_skill_learns_an_independent_veto_policy(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    configuration = "baseline-v1.2-manipulation-config"
    rows: list[tuple[LearningObservation, float]] = []
    for index in range(80):
        manipulated = index % 2 == 0
        observed_at = now + timedelta(minutes=index * 10)
        mint = f"manipulation-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        for feature_name in (
            "round_trip_wallet_ratio",
            "round_trip_volume_ratio",
            "side_alternation_ratio",
            "quantized_amount_repeat_ratio",
        ):
            decision.feature_snapshot.values[feature_name] = data(
                observed_at, 0.95 if manipulated else 0.05
            )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        outcome = -0.40 if manipulated else 0.20
        resolve_policy_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            outcome,
        )
        rows.append((learner.observations[mint], outcome))

    learner._publish_manipulation_artifact(  # noqa: SLF001 - validate skill boundary
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        rows=rows,
        training=rows[:60],
        validation=rows[60:],
        resolved_count=len(rows),
        embargoed_count=0,
    )
    artifacts = [
        artifact
        for artifact in learner.skill_artifacts.values()
        if artifact.skill.value == "manipulation"
    ]
    assert len(artifacts) == 1
    specialist = artifacts[0]
    assert specialist.qualified is True
    assert specialist.metrics["policy_vetoes"] == 10
    assert specialist.metrics["policy_winner_vetoes"] == 0
    state = next(
        state for state in learner.skill_states.values() if state.skill.value == "manipulation"
    )
    assert state.champion_version == specialist.version

    future = make_decision(now + timedelta(minutes=30), "manipulation-future").model_copy(
        update={
            "model_version": BASELINE_VERSION,
            "configuration_fingerprint": configuration,
        }
    )
    for feature_name in (
        "round_trip_wallet_ratio",
        "round_trip_volume_ratio",
        "side_alternation_ratio",
        "quantized_amount_repeat_ratio",
    ):
        future.feature_snapshot.values[feature_name] = data(future.created_at, 0.95)
    assert learner.register(
        future,
        make_state(future.mint),
        live=True,
        evaluation_actionable=True,
    )
    receipt = learner.observations[future.mint].challenger_evaluations[specialist.version]
    assert receipt.skill.value == "manipulation"
    assert receipt.proposed_action == "veto"
    database.close()


def test_sizing_skill_learns_only_from_bounded_executable_size_trials(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    configuration = "baseline-v1.2-sizing-config"
    rows: list[tuple[LearningObservation, float]] = []
    for index in range(80):
        strong = index % 2 == 0
        observed_at = now + timedelta(minutes=index * 10)
        mint = f"sizing-{index}"
        decision = make_decision(
            observed_at,
            mint,
            opportunity=0.95 if strong else 0.15,
        ).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        observation = learner.observations[mint]
        episode = policy_episode_for(learner, mint)
        baseline_cost = episode.size_trials["1"].entry_cost_lamports
        assert baseline_cost is not None
        for trial in episode.size_trials.values():
            if not trial.eligible_at_entry or trial.entry_cost_lamports is None:
                continue
            normalized_profit = trial.multiplier * (0.10 if strong else -0.10)
            exit_value = max(
                0,
                int(trial.entry_cost_lamports + baseline_cost * normalized_profit),
            )
            trial.checkpoints["300"] = LearningCheckpoint(
                horizon_seconds=300,
                observed_at=observed_at + timedelta(seconds=300),
                net_return=(exit_value - trial.entry_cost_lamports) / trial.entry_cost_lamports,
                exit_value_lamports=exit_value,
            )
        resolve_policy_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            0.10 if strong else -0.10,
        )
        rows.append((observation, 0.10 if strong else -0.10))

    learner._publish_sizing_artifact(  # noqa: SLF001 - validate sizing proof boundary
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        rows=rows,
        training=rows[:60],
        validation=rows[60:],
        embargoed_count=0,
    )
    specialist = next(
        artifact
        for artifact in learner.skill_artifacts.values()
        if artifact.skill.value == "sizing"
    )
    assert specialist.qualified is True
    assert specialist.metrics["policy_changes"] == specialist.validation_count
    assert specialist.metrics["harm_count"] == 0
    state = next(state for state in learner.skill_states.values() if state.skill.value == "sizing")
    assert state.champion_version == specialist.version

    future = make_decision(
        now + timedelta(minutes=30),
        "sizing-future",
        opportunity=0.95,
    ).model_copy(
        update={
            "model_version": BASELINE_VERSION,
            "configuration_fingerprint": configuration,
        }
    )
    assert learner.register(
        future,
        make_state(future.mint),
        live=True,
        evaluation_actionable=True,
    )
    receipt = learner.observations[future.mint].challenger_evaluations[specialist.version]
    assert receipt.skill.value == "sizing"
    assert receipt.proposed_action == "2"
    assert set(learner.observations[future.mint].size_trials) == {"0.5", "1", "1.5", "2"}
    database.close()


def test_exit_skill_can_only_qualify_an_earlier_bounded_review(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    configuration = "baseline-v1.2-exit-config"
    for index in range(60):
        observed_at = now + timedelta(minutes=index * 20)
        mint = f"exit-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        observation = learner.observations[mint]
        episode = policy_episode_for(learner, mint)
        for horizon, outcome in ((60, 0.20), (300, 0.10), (600, 0.0)):
            checkpoint = LearningCheckpoint(
                horizon_seconds=horizon,
                observed_at=observed_at + timedelta(seconds=horizon),
                net_return=outcome,
                exit_value_lamports=1,
            )
            observation.checkpoints[str(horizon)] = checkpoint
            episode.checkpoints[str(horizon)] = checkpoint.model_copy(deep=True)
        database.save_learning_evidence_episode(episode)

    learner._publish_exit_artifact(  # noqa: SLF001 - validate independent exit proof
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
    )
    specialist = next(
        artifact for artifact in learner.skill_artifacts.values() if artifact.skill.value == "exit"
    )
    assert specialist.qualified is True
    assert specialist.parameters["selected_horizon_seconds"] == 60
    assert specialist.parameters["baseline_horizon_seconds"] == 600
    assert specialist.parameters["hard_max_hold_seconds"] == 1_800
    state = next(state for state in learner.skill_states.values() if state.skill.value == "exit")
    assert state.champion_version == specialist.version

    future = make_decision(now + timedelta(days=2), "exit-future").model_copy(
        update={
            "model_version": BASELINE_VERSION,
            "configuration_fingerprint": configuration,
        }
    )
    assert learner.register(
        future,
        make_state(future.mint),
        live=True,
        evaluation_actionable=True,
    )
    receipt = learner.observations[future.mint].challenger_evaluations[specialist.version]
    assert receipt.skill.value == "exit"
    assert receipt.proposed_action == "60"
    database.close()


def test_one_consent_activates_entry_and_later_skill_joins_only_after_common_proof(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "baseline-v1.2-consent-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    entry_model = qualified_model("consent-entry", 0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        entry_model,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    learner.entry_outcome_availability = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "qualified": True,
        "observed_count": 80,
        "available_count": 80,
        "availability_fraction": 1.0,
        "minimum_fraction": 0.7,
    }
    learner.set_mode(LearningMode.ACTIVE)
    assert learner.consent_granted is True
    assert database.get_setting("challenger_consent_granted") is True
    assert set(learner.active_skill_versions) == {"entry"}

    cohort_key = next(
        state.cohort_key
        for state in learner.skill_states.values()
        if state.skill == ChallengerSkill.ENTRY
    )
    manipulation = ChallengerSkillArtifact(
        version="challenger-skill-v1-manipulation-consent",
        skill=ChallengerSkill.MANIPULATION,
        created_at=now + timedelta(seconds=1),
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        outcomes_seen=80,
        sample_count=80,
        training_count=60,
        validation_count=20,
        feature_names=list(MANIPULATION_FEATURE_NAMES),
        parameters={
            "means": [0.0] * len(MANIPULATION_FEATURE_NAMES),
            "scales": [1.0] * len(MANIPULATION_FEATURE_NAMES),
            "coefficients": [-0.20, *([0.0] * len(MANIPULATION_FEATURE_NAMES))],
        },
        metrics={"validation_rmse": 0.05},
        qualified=True,
    )
    learner._register_skill_artifact(manipulation, cohort_key)  # noqa: SLF001
    for index in range(30):
        observed_at = now + timedelta(minutes=10 + index)
        mint = f"join-proof-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        resolve_forward_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            -0.10,
        )
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert set(learner.active_skill_versions) == {"entry", "manipulation"}
    assert database.get_setting("active_challenger_skills") == learner.active_skill_versions
    status = learner.status(demo_mode=False)
    assert status["consent_granted"] is True
    assert set(status["active_skill_versions"]) == {"entry", "manipulation"}
    skill_statuses = {item["skill"]: item for item in status["skills"]}
    assert set(skill_statuses) == {"entry", "manipulation", "sizing", "exit"}
    assert skill_statuses["entry"]["state"] == "active"
    assert skill_statuses["manipulation"]["state"] == "active"
    # The join proof is consumed at activation, so its durable counter resets for the next
    # candidate instead of presenting old evidence as a future tournament.
    assert skill_statuses["manipulation"]["common_forward_count"] == 0
    assert skill_statuses["sizing"]["state"] == "collecting"
    assert skill_statuses["exit"]["state"] == "collecting"

    assessed = learner.assess(
        make_decision(now + timedelta(days=1), "consent-assess").model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        ),
        live=True,
        baseline_actionable=True,
    )
    assert assessed.action == DecisionAction.PASS
    assert "challenger_manipulation_veto" in assessed.blockers
    assert set(assessed.challenger_assessments) == {"entry", "manipulation"}

    learner.set_risk_mode(RiskMode.BALANCED)
    assert learner.mode == LearningMode.ACTIVE
    assert set(learner.active_skill_versions) == {"entry", "manipulation"}
    learner.set_risk_mode(RiskMode.SAFE)
    assert learner.mode == LearningMode.SHADOW
    assert learner.active_skill_versions == {}
    assert learner.consent_granted is True
    database.close()


def test_active_sizing_cannot_invent_entry_or_size_up_uncertain_integrity(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "baseline-v1.3-sizing-active-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    entry_model = qualified_model("sizing-entry", 0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        entry_model,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    learner.entry_outcome_availability = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "qualified": True
    }
    learner.set_mode(LearningMode.ACTIVE)
    cohort_key = next(iter(learner.skill_states.values())).cohort_key
    sizing = ChallengerSkillArtifact(
        version="challenger-skill-v1-sizing-active",
        skill=ChallengerSkill.SIZING,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=list(SIZING_FEATURE_NAMES),
        parameters={
            "means": [0.0] * len(SIZING_FEATURE_NAMES),
            "scales": [1.0] * len(SIZING_FEATURE_NAMES),
            "coefficients": [2.0, *([0.0] * len(SIZING_FEATURE_NAMES))],
        },
        qualified=True,
    )
    learner._register_skill_artifact(sizing, cohort_key)  # noqa: SLF001
    learner._activate_skill(sizing)  # noqa: SLF001

    baseline = make_decision(now, "sizing-active").model_copy(
        update={
            "model_version": BASELINE_VERSION,
            "configuration_fingerprint": configuration,
        }
    )
    uncertain = learner.assess(baseline, live=True, baseline_actionable=True)
    assert uncertain.planned_order_size_sol == baseline.planned_order_size_sol
    assert uncertain.challenger_assessments["sizing"]["proposed_action"] == (
        "baseline_integrity_guard"
    )

    clean = baseline.model_copy(
        update={
            "integrity_assessment": IntegrityAssessment(
                policy_version="test",
                state=MarketIntegrityState.CLEAN,
                score=0.0,
                coverage=1.0,
                sample_count=20,
                category_count=4,
            ),
            "sizing_assessment": SizingAssessment(
                policy_version="test",
                base_size_sol=0.025,
                desired_size_sol=0.025,
                selected_size_sol=0.025,
                maximum_size_sol=0.04,
                account_allocation_fraction=0.01,
            ),
        }
    )
    capacity_guarded = learner.assess(clean, live=True, baseline_actionable=True)
    assert capacity_guarded.planned_order_size_sol == clean.planned_order_size_sol
    assert capacity_guarded.challenger_assessments["sizing"]["proposed_action"] == (
        "baseline_capacity_guard"
    )
    assert capacity_guarded.challenger_assessments["sizing"]["parameters"]["applied"] is False

    assert clean.sizing_assessment is not None
    clean.sizing_assessment.maximum_size_sol = 0.05
    sized = learner.assess(clean, live=True, baseline_actionable=True)
    assert sized.planned_order_size_sol == pytest.approx(0.05)
    passed = learner.assess(
        clean.model_copy(update={"action": DecisionAction.PASS}),
        live=True,
        baseline_actionable=False,
    )
    assert passed.action == DecisionAction.PASS
    assert passed.planned_order_size_sol == clean.planned_order_size_sol

    entry_version = learner.active_skill_versions["entry"]
    sizing_state = learner._current_skill_state(ChallengerSkill.SIZING)  # noqa: SLF001
    assert sizing_state is not None
    sizing_state.active_dependencies = {
        "entry": entry_version,
        "manipulation": "missing-manipulation-dependency",
    }
    database.save_challenger_skill_state(sizing_state)
    runtime_guarded = learner.assess(clean, live=True, baseline_actionable=True)
    assert "sizing" not in runtime_guarded.challenger_assessments
    dependency_restart = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    assert dependency_restart.mode == LearningMode.ACTIVE
    assert dependency_restart.active_skill_versions == {"entry": entry_version}

    database.set_setting(
        "active_challenger_skills",
        {"entry": "missing-entry-artifact", "sizing": sizing.version},
    )
    database.set_setting("learning_mode", LearningMode.ACTIVE.value)
    restarted = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    assert restarted.mode == LearningMode.SHADOW
    assert restarted.active_skill_versions == {}
    database.close()


def test_locked_previous_baseline_keeps_its_exact_active_challenger_cohort(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "locked-baseline-v1.2-cohort"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
        baseline_version=lambda: PREVIOUS_BASELINE_VERSION,
    )
    now = datetime.now(UTC)
    entry_model = qualified_model("previous-entry", 0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        entry_model,
        baseline_version=PREVIOUS_BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    learner.entry_outcome_availability = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "qualified": True
    }
    learner.set_mode(LearningMode.ACTIVE)
    assert learner.active_skill_versions.keys() == {"entry"}

    restarted = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
        baseline_version=lambda: PREVIOUS_BASELINE_VERSION,
    )
    assert restarted.mode == LearningMode.ACTIVE
    assert restarted.active_skill_versions == learner.active_skill_versions
    state = restarted._current_skill_state(ChallengerSkill.ENTRY)  # noqa: SLF001
    assert state is not None
    assert state.baseline_version == PREVIOUS_BASELINE_VERSION
    database.close()


def test_new_upstream_skill_deactivates_downstream_until_fresh_join_proof(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "baseline-v1.2-upstream-join-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    entry_model = qualified_model("upstream-entry", 0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        entry_model,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    learner.entry_outcome_availability = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "qualified": True
    }
    learner.set_mode(LearningMode.ACTIVE)
    cohort_key = next(iter(learner.skill_states.values())).cohort_key
    exit_artifact = ChallengerSkillArtifact(
        version="challenger-skill-v1-exit-active-before-sizing",
        skill=ChallengerSkill.EXIT,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        parameters={
            "selected_horizon_seconds": 300,
            "baseline_horizon_seconds": 600,
            "hard_max_hold_seconds": 1_800,
        },
        qualified=True,
    )
    learner._register_skill_artifact(exit_artifact, cohort_key)  # noqa: SLF001
    learner._activate_skill(exit_artifact)  # noqa: SLF001
    assert set(learner.active_skill_versions) == {"entry", "exit"}

    sizing_artifact = ChallengerSkillArtifact(
        version="challenger-skill-v1-sizing-joins-after-exit",
        skill=ChallengerSkill.SIZING,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=["opportunity"],
        parameters={
            "means": [0.0],
            "scales": [1.0],
            "coefficients": [1.0, 0.0],
        },
        qualified=True,
    )
    learner._register_skill_artifact(sizing_artifact, cohort_key)  # noqa: SLF001
    learner._activate_skill(sizing_artifact)  # noqa: SLF001

    assert set(learner.active_skill_versions) == {"entry", "sizing"}
    exit_state = learner._current_skill_state(ChallengerSkill.EXIT)  # noqa: SLF001
    assert exit_state is not None
    assert exit_state.champion_version == exit_artifact.version
    assert exit_state.active_version is None
    assert exit_state.last_tournament["result"] == "dependency_activated"
    assert exit_state.last_tournament["dependency"] == "sizing"
    restarted = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    assert set(restarted.active_skill_versions) == {"entry", "sizing"}
    database.close()


def test_harmful_active_entry_skill_suspends_without_revoking_consent(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "baseline-v1.2-suspension-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    harmful = qualified_model("harmful-active-entry", -0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        harmful,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    learner.entry_outcome_availability = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "qualified": True
    }
    learner.set_mode(LearningMode.ACTIVE)
    active_version = learner.active_skill_versions["entry"]
    for index in range(30):
        observed_at = now + timedelta(minutes=10 + index)
        mint = f"active-harm-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        resolve_forward_primary(
            learner,
            mint,
            observed_at + timedelta(seconds=300),
            0.10,
        )
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.mode == LearningMode.SHADOW
    assert learner.active_skill_versions == {}
    assert learner.consent_granted is True
    state = next(
        state for state in learner.skill_states.values() if state.skill == ChallengerSkill.ENTRY
    )
    assert state.suspended_version == active_version
    assert state.suspension_reason == "degraded"
    suspended_status = next(
        item for item in learner.skill_statuses() if item["skill"] == ChallengerSkill.ENTRY.value
    )
    assert suspended_status["state"] == "suspended"
    assert suspended_status["health"]["state"] == "suspended"
    restarted = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    assert restarted.mode == LearningMode.SHADOW
    assert restarted.active_skill_versions == {}
    assert restarted.consent_granted is True
    restarted_status = next(
        item for item in restarted.skill_statuses() if item["skill"] == ChallengerSkill.ENTRY.value
    )
    assert restarted_status["state"] == "suspended"
    assert restarted_status["health"]["state"] == "suspended"
    database.close()


def test_pending_active_outcomes_do_not_count_as_unverifiable_health(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "baseline-v1.2-pending-health-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    entry_model = qualified_model("pending-health-entry", 0.2, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        entry_model,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    learner.entry_outcome_availability = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "qualified": True
    }
    learner.set_mode(LearningMode.ACTIVE)
    active_version = learner.active_skill_versions["entry"]

    for index in range(30):
        created_at = now + timedelta(seconds=index)
        mint = f"pending-health-{index}"
        decision = make_decision(created_at, mint).model_copy(
            update={
                "model_version": BASELINE_VERSION,
                "configuration_fingerprint": configuration,
            }
        )
        assert learner.register(
            decision,
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )

    health = learner._skill_health(ChallengerSkill.ENTRY, active_version)  # noqa: SLF001
    assert health["observed_count"] == 0
    assert health["state"] == "collecting"

    for mint, observation in learner.observations.items():
        resolve_forward_primary(
            learner,
            mint,
            observation.created_at + timedelta(seconds=390),
            None,
            missing_reason="stale_cached_route",
        )
    health = learner._skill_health(ChallengerSkill.ENTRY, active_version)  # noqa: SLF001
    assert health["observed_count"] == 30
    assert health["availability_fraction"] == 0
    assert health["state"] == "unverifiable"
    database.close()


def test_incomplete_integrity_evidence_never_becomes_zero_filled_learning(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    decision = make_decision(now, "missing-integrity")
    decision.feature_snapshot.values["round_trip_volume_ratio"] = DataValue(
        value=None,
        unit="fraction",
        as_of=now,
        sources=["test"],
        freshness_seconds=0,
        quality=0.2,
        missing_reason="wallet_or_trade_amount_unavailable",
    )

    assert learner.register(decision, make_state(decision.mint), live=True) is False
    assert decision.mint not in learner.observations
    database.close()


def test_actionable_policy_evidence_is_not_blocked_by_an_earlier_pass(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: "config-one",
    )
    now = datetime.now(UTC)
    mint = "pass-then-actionable"
    state = make_state(mint)
    first_pass = make_decision(now, mint).model_copy(
        update={
            "decision_id": "decision-pass-first",
            "action": DecisionAction.PASS,
            "season_id": "season-one",
            "configuration_fingerprint": "config-one",
        }
    )
    assert learner.register(first_pass, state, live=True, evaluation_actionable=False)
    assert learner.observations[mint].baseline_action == DecisionAction.PASS
    # Let the discovery-only PASS finish first. A later actionable entry must still advance
    # training and Champion proof from its independent policy journal.
    learner.observe_market(state, now + timedelta(seconds=1_200), live=True)
    assert learner.observations[mint].status == LearningObservationStatus.COMPLETE
    with learner._training_request_lock:  # noqa: SLF001 - isolate the later policy signal
        learner._training_requests.clear()  # noqa: SLF001

    actionable = make_decision(now + timedelta(seconds=1_300), mint).model_copy(
        update={
            "decision_id": "decision-enter-later",
            "season_id": "season-one",
            "configuration_fingerprint": "config-one",
        }
    )
    assert learner.register(actionable, state, live=True, evaluation_actionable=True)
    episodes = database.list_learning_evidence_episodes()
    assert len(episodes) == 1
    assert episodes[0].lane == LearningEvidenceLane.POLICY
    assert episodes[0].status == LearningEvidenceStatus.PENDING
    assert episodes[0].decision_id == actionable.decision_id
    assert episodes[0].qualification_eligible is True

    # Repeated decisions in one mint-season trajectory cannot manufacture sample size.
    repeated = actionable.model_copy(
        update={
            "decision_id": "decision-enter-repeated",
            "created_at": actionable.created_at + timedelta(seconds=30),
        }
    )
    assert learner.register(repeated, state, live=True, evaluation_actionable=True) is False
    assert len(database.list_learning_evidence_episodes()) == 1
    status = learner.status(demo_mode=False)
    lanes = {lane["id"]: lane for lane in status["evidence_lanes"]}
    assert lanes["discovery"]["qualification_role"] == "proposal"
    assert lanes["policy"] == {
        "id": "policy",
        "label": "Policy proof",
        "purpose": "Judges untouched Baseline entries in this exact personality.",
        "observed_count": 1,
        "usable_count": 0,
        "pending_count": 1,
        "unavailable_count": 0,
        "qualification_role": "authoritative",
    }
    assert lanes["execution"]["qualification_role"] == "audit"
    assert status["evidence_contract"]["collection_started_at"] == actionable.created_at.isoformat()
    assert learner.has_pending_training() is False
    learner.observe_market(
        state,
        actionable.created_at + timedelta(seconds=300),
        live=True,
    )
    assert policy_episode_for(learner, mint).checkpoints["300"].net_return is not None
    assert learner.has_pending_training() is True
    episode_id = episodes[0].episode_id
    monkeypatch.setattr(database, "prune_learning_observations", lambda _limit: [])
    monkeypatch.setattr(database, "prune_learning_evidence", lambda _limit: [episode_id])
    learner._prune_complete_history()  # noqa: SLF001 - memory/storage pruning boundary
    assert episode_id not in learner.evidence_episodes
    assert mint not in learner._evidence_episode_ids_by_mint  # noqa: SLF001
    database.close()


def test_policy_proof_is_unique_by_mint_and_disjoint_from_discovery_training(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "independent-proof-config"
    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    now = datetime.now(UTC)
    mint = "repeat-across-seasons"
    state = make_state(mint)

    first = make_decision(now, mint).model_copy(
        update={
            "decision_id": "independent-first",
            "season_id": "season-one",
            "configuration_fingerprint": configuration,
        }
    )
    assert learner.register(first, state, live=True, evaluation_actionable=True)
    resolve_forward_primary(learner, mint, now + timedelta(seconds=300), 0.05)

    second = make_decision(now + timedelta(hours=1), mint).model_copy(
        update={
            "decision_id": "independent-second",
            "season_id": "season-two",
            "configuration_fingerprint": configuration,
        }
    )
    assert learner.register(second, state, live=True, evaluation_actionable=True)
    episodes = [
        episode
        for episode in learner.evidence_episodes.values()
        if episode.lane == LearningEvidenceLane.POLICY and episode.mint == mint
    ]
    assert len(episodes) == 2  # Both seasons remain auditable.
    assert (
        len(
            learner._policy_evidence(  # noqa: SLF001 - proof independence boundary
                mode=RiskMode.BALANCED,
                configuration_fingerprint=configuration,
                baseline_version=BASELINE_VERSION,
            )
        )
        == 1
    )
    assert (
        learner._policy_evidence(  # noqa: SLF001 - cutoff must not enable a second attempt
            mode=RiskMode.BALANCED,
            configuration_fingerprint=configuration,
            baseline_version=BASELINE_VERSION,
            not_before=now + timedelta(minutes=30),
        )
        == []
    )
    assert (
        learner._training_rows(  # noqa: SLF001 - lane separation boundary
            mode=RiskMode.BALANCED,
            configuration_fingerprint=configuration,
            match_configuration=True,
        )
        == []
    )

    discovery_mint = "discovery-only"
    discovery = make_decision(now + timedelta(hours=2), discovery_mint).model_copy(
        update={
            "decision_id": "discovery-only-decision",
            "action": DecisionAction.PASS,
            "season_id": "season-two",
            "configuration_fingerprint": configuration,
        }
    )
    assert learner.register(
        discovery,
        make_state(discovery_mint),
        live=True,
        evaluation_actionable=False,
    )
    learner.observations[discovery_mint].checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=discovery.created_at + timedelta(seconds=300),
        net_return=0.02,
        exit_value_lamports=1_020_000,
    )
    rows = learner._training_rows(  # noqa: SLF001 - lane separation boundary
        mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        match_configuration=True,
    )
    assert [observation.mint for observation, _ in rows] == [discovery_mint]
    scorecard = learner.baseline_scorecard()
    assert scorecard["changes_policy"] is False
    assert scorecard["policy"]["observed_count"] == 1
    assert scorecard["policy"]["usable_count"] == 1
    assert scorecard["policy"]["median_return"] == 0.05
    assert scorecard["policy"]["cost_basis"] == ("modeled_entry_exit_protocol_and_network_costs")
    database.close()


def test_policy_and_discovery_checkpoints_enforce_real_quote_reserves(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    mint = "real-quote-guard"
    state = make_state(mint)
    state.real_quote_reserves = 1
    decision = make_decision(now, mint).model_copy(
        update={
            "season_id": "season-real-quote",
            "configuration_fingerprint": "config-real-quote",
        }
    )
    assert learner.register(decision, state, live=True, evaluation_actionable=True)

    assert learner.observe_market(state, now + timedelta(seconds=300), live=True) == 4
    discovery = learner.observations[mint].checkpoints["300"]
    policy = next(iter(learner.evidence_episodes.values())).checkpoints["300"]
    assert discovery.net_return is None
    assert policy.net_return is None
    assert discovery.missing_reason == "executable_exit_quote_unavailable"
    assert policy.missing_reason == "executable_exit_quote_unavailable"
    database.close()


def test_missing_horizon_is_unknown_not_a_loss(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    state = make_state("mint-missing")
    assert learner.register(make_decision(now, "mint-missing"), state, live=True)

    learner.expire_checkpoints(now + timedelta(seconds=391))
    checkpoint = learner.observations["mint-missing"].checkpoints["300"]
    assert checkpoint.net_return is None
    assert checkpoint.missing_reason == "no_fresh_trade_near_horizon"
    status = learner.status(demo_mode=False)
    assert status["usable_outcome_count"] == 0
    assert status["challenger_interval_outcomes"] == 10
    assert status["demo_excluded"] is True
    database.close()


def test_unquotable_primary_outcome_immediately_advances_health_governance(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    mint = "unquotable-primary"
    assert learner.register(make_decision(now, mint), make_state(mint), live=True)
    bad_route = make_state(mint)
    monkeypatch.setattr(
        "signal_arcade.intelligence.learning.quote_sell",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("unquotable")),
    )
    calls = {"govern": 0}
    monkeypatch.setattr(
        learner,
        "_govern_skill_ensemble",
        lambda: calls.__setitem__("govern", calls["govern"] + 1),
    )

    assert learner.observe_market(bad_route, now + timedelta(seconds=300), live=True) == 2
    checkpoint = learner.observations[mint].checkpoints["300"]
    assert checkpoint.net_return is None
    assert checkpoint.missing_reason == "executable_exit_quote_unavailable"
    assert calls["govern"] == 1
    database.close()


def test_missing_liquidity_reduces_horizon_utility_without_fabricating_pnl(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    for index in range(3):
        mint = f"horizon-{index}"
        assert learner.register(make_decision(now, mint), make_state(mint), live=True)
        observation = learner.observations[mint]
        observation.checkpoints["300"] = LearningCheckpoint(
            horizon_seconds=300,
            observed_at=now + timedelta(seconds=300),
            net_return=0.5 if index < 2 else None,
            exit_value_lamports=1_500_000 if index < 2 else None,
            missing_reason=None if index < 2 else "no_fresh_trade_near_horizon",
        )

    performance = next(
        item for item in learner.horizon_performance() if item["horizon_seconds"] == 300
    )

    assert performance["observed_count"] == 3
    assert performance["available_count"] == 2
    assert performance["availability_fraction"] == pytest.approx(2 / 3)
    assert performance["mean_net_return"] == 0.5
    assert performance["conservative_utility"] < performance["mean_net_return"]
    assert learner.status(demo_mode=False)["usable_outcome_count"] == 2
    database.close()


def test_hold_timing_earns_separate_chronological_validation(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC) - timedelta(hours=2)
    for index in range(60):
        mint = f"timing-{index}"
        created_at = now + timedelta(minutes=index)
        assert learner.register(
            make_decision(created_at, mint).model_copy(update={"risk_mode": RiskMode.SAFE}),
            make_state(mint),
            live=True,
        )
        observation = learner.observations[mint]
        observation.checkpoints = {
            "60": LearningCheckpoint(
                horizon_seconds=60,
                observed_at=created_at + timedelta(seconds=60),
                net_return=0.20,
                exit_value_lamports=1_200_000,
            ),
            "300": LearningCheckpoint(
                horizon_seconds=300,
                observed_at=created_at + timedelta(seconds=300),
                net_return=-0.20,
                exit_value_lamports=800_000,
            ),
        }

    qualified = learner.hold_timing_validation(RiskMode.SAFE)

    assert qualified["qualified"] is True
    assert qualified["selected_horizon_seconds"] == 60
    assert qualified["baseline_horizon_seconds"] == 300
    assert qualified["selected_validation_utility"] > qualified["baseline_validation_utility"]
    assert learner.hold_timing_validation(RiskMode.BALANCED)["sample_count"] == 0

    for observation in sorted(learner.observations.values(), key=lambda item: item.created_at)[-7:]:
        observation.checkpoints["60"] = LearningCheckpoint(
            horizon_seconds=60,
            observed_at=observation.created_at + timedelta(seconds=150),
            missing_reason="no_fresh_trade_near_horizon",
        )
    # This fixture mutates internal history directly rather than using observe_market(), whose
    # production path invalidates the cached chronological assessment automatically.
    learner._invalidate_timing_validation()

    availability_blocked = learner.hold_timing_validation(RiskMode.SAFE)

    assert availability_blocked["qualified"] is False
    assert availability_blocked["validation_availability_fraction"] < 0.70
    database.close()


def test_completed_learning_history_is_bounded_without_deleting_pending(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC)
    for index in range(3):
        mint = f"complete-{index}"
        assert learner.register(
            make_decision(now + timedelta(seconds=index), mint), make_state(mint), live=True
        )
        observation = learner.observations[mint]
        observation.status = LearningObservationStatus.COMPLETE
        database.save_learning_observation(observation)
    assert learner.register(
        make_decision(now + timedelta(seconds=4), "still-pending"),
        make_state("still-pending"),
        live=True,
    )

    removed = database.prune_learning_observations(2)

    assert removed == ["complete-0"]
    remaining = {item.mint for item in database.list_learning_observations()}
    assert remaining == {"complete-1", "complete-2", "still-pending"}
    database.close()


def test_model_history_keeps_protected_and_newest_versions(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    models = [qualified_model(f"history-{index}", 0.2, index + 1) for index in range(3)]
    for index, model in enumerate(models):
        model.created_at = datetime.now(UTC) + timedelta(seconds=index)
        database.save_learning_model(model)

    removed = database.prune_learning_models(2, preserve_versions={models[0].version})

    assert removed == [models[1].version]
    assert {model.version for model in database.list_learning_models()} == {
        models[0].version,
        models[2].version,
    }
    database.close()


@pytest.mark.parametrize(
    "legacy_version",
    [
        "learner-v1-80-legacy",
        "learner-v3-80-pre-integrity",
        "learner-v4-80-pre-policy-journal",
    ],
)
def test_legacy_refit_model_cannot_be_newly_activated(
    settings,
    legacy_version: str,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    legacy = qualified_model("legacy", 0.2, 80).model_copy(update={"version": legacy_version})
    database.save_learning_model(legacy)
    learner = LearningEngine(database, settings)

    unavailable_status = learner.status(demo_mode=False)
    assert unavailable_status["activation_available"] is False
    unavailable_gates = {gate["id"]: gate for gate in unavailable_status["qualification_gates"]}
    assert unavailable_gates["current_outcome_availability"]["state"] == "not_met"
    assert unavailable_gates["activation_ready"]["state"] == "not_met"
    assert unavailable_status["qualification_passed"] < unavailable_status["qualification_total"]
    with pytest.raises(ValueError, match="newest challenger"):
        learner.set_mode(LearningMode.ACTIVE)
    database.close()


def test_claimed_qualified_model_without_policy_proof_cannot_activate(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    weak = qualified_model("missing-policy-proof", 0.2, 80).model_copy(
        update={
            "policy_validation_count": 100,
            "policy_veto_count": 0,
            "policy_uplift_lower_bound": 0.2,
        }
    )
    database.save_learning_model(weak)
    learner = LearningEngine(database, settings)

    assert learner.status(demo_mode=False)["activation_available"] is False
    with pytest.raises(ValueError, match="newest challenger"):
        learner.set_mode(LearningMode.ACTIVE)
    database.close()


@pytest.mark.parametrize(
    "unsafe_update",
    [
        {"qualification_evidence_schema_version": None},
        {"policy_outcome_availability_fraction": 0.69},
        {"policy_supported_count": 9},
        {"policy_winner_veto_fraction": 0.36},
    ],
)
def test_entry_model_fails_closed_on_incomplete_or_over_vetoing_policy_proof(
    settings,
    unsafe_update: dict[str, object],
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    safe = qualified_model("complete-policy-proof", 0.2, 80)
    assert learner._model_is_eligible(safe) is True  # noqa: SLF001

    unsafe = safe.model_copy(update=unsafe_update)

    assert learner._model_is_eligible(unsafe) is False  # noqa: SLF001
    database.close()


def test_malformed_model_falls_back_without_affecting_a_decision(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    malformed = qualified_model("malformed", -0.5, 80).model_copy(
        update={"feature_names": ["opportunity"]}
    )
    database.save_learning_model(malformed)
    learner = LearningEngine(database, settings)
    decision = make_decision(datetime.now(UTC), "malformed-safe-fallback")

    assessed = learner.assess(decision, live=True)

    assert assessed.action == DecisionAction.ENTER
    assert assessed.learning_assessment is None
    assert learner.status(demo_mode=False)["activation_available"] is False
    database.close()


def test_entry_activation_requires_recent_executable_outcome_availability(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    candidate = qualified_model("availability-gated", 0.2, 80)
    database.save_learning_model(candidate)
    learner = LearningEngine(database, settings)
    now = datetime.now(UTC) - timedelta(days=1)
    for index in range(115):
        mint = f"availability-{index}"
        created_at = now + timedelta(minutes=index)
        assert learner.register(make_decision(created_at, mint), make_state(mint), live=True)
        learner.observations[mint].checkpoints["300"] = LearningCheckpoint(
            horizon_seconds=300,
            observed_at=created_at + timedelta(seconds=300),
            net_return=0.1 if index < 80 else None,
            exit_value_lamports=1_100_000 if index < 80 else None,
            missing_reason=None if index < 80 else "executable_exit_quote_unavailable",
        )

    availability = learner.entry_outcome_availability()
    assert availability["availability_fraction"] < 0.70
    unavailable_status = learner.status(demo_mode=False)
    assert unavailable_status["activation_available"] is False
    unavailable_gates = {gate["id"]: gate for gate in unavailable_status["qualification_gates"]}
    assert unavailable_gates["current_outcome_availability"]["state"] == "not_met"
    assert unavailable_gates["activation_ready"]["state"] == "not_met"
    assert unavailable_status["qualification_passed"] < unavailable_status["qualification_total"]
    with pytest.raises(ValueError, match="forward and suspension gates"):
        learner.set_mode(LearningMode.ACTIVE)

    recovered = learner.observations["availability-80"].checkpoints["300"]
    recovered.net_return = 0.1
    recovered.exit_value_lamports = 1_100_000
    recovered.missing_reason = None
    assert learner.entry_outcome_availability()["availability_fraction"] >= 0.70
    recovered_status = learner.status(demo_mode=False)
    assert recovered_status["activation_available"] is True
    recovered_gates = {gate["id"]: gate for gate in recovered_status["qualification_gates"]}
    assert recovered_gates["current_outcome_availability"]["state"] == "passed"
    assert recovered_gates["activation_ready"]["state"] == "passed"
    database.close()


def test_active_model_is_suspended_after_confident_unseen_harm(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    champion = qualified_model("harmful-champion", -0.5, 1)
    database.save_learning_model(champion)
    learner = LearningEngine(database, settings)
    learner._activate_model(champion)
    learner.mode = LearningMode.ACTIVE
    now = datetime.now(UTC) - timedelta(hours=8)

    for index in range(30):
        mint = f"health-harm-{index}"
        created_at = now + timedelta(minutes=10 * index)
        assert learner.register(
            make_decision(created_at, mint),
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        winner = make_state(mint)
        winner.virtual_quote_reserves = 45_000_000_000
        learner.observe_market(winner, created_at + timedelta(seconds=300), live=True)

    health = learner.status(demo_mode=False)["active_model_health"]
    assert learner.mode == LearningMode.SHADOW
    assert learner.active_model is None
    assert health["state"] == "suspended"
    assert health["model_version"] == champion.version
    assert health["winner_vetoed_count"] == 30
    assert health["uplift_upper_bound"] < -0.01
    assert learner.status(demo_mode=False)["activation_available"] is False
    with pytest.raises(ValueError, match="newest challenger"):
        learner.set_mode(LearningMode.ACTIVE)

    database.close()
    recovered_database = Database(settings.database_path)
    recovered = LearningEngine(recovered_database, settings)
    assert recovered.mode == LearningMode.SHADOW
    assert recovered.status(demo_mode=False)["active_model_health"]["state"] == "suspended"
    recovered_database.close()


def test_active_model_is_suspended_when_forward_health_is_unverifiable(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    champion = qualified_model("unverifiable-champion", 0.5, 1)
    database.save_learning_model(champion)
    learner = LearningEngine(database, settings)
    learner._activate_model(champion)
    learner.mode = LearningMode.ACTIVE
    now = datetime.now(UTC) - timedelta(hours=2)
    for index in range(30):
        mint = f"health-missing-{index}"
        assert learner.register(
            make_decision(now, mint),
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )

    learner.expire_checkpoints(now + timedelta(seconds=391))

    health = learner.status(demo_mode=False)["active_model_health"]
    assert learner.mode == LearningMode.SHADOW
    assert health["state"] == "suspended"
    assert health["suspension_reason"] == "unverifiable"
    assert health["availability_fraction"] == 0
    database.close()


def test_portfolio_blocked_entries_do_not_credit_or_harm_active_model(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    champion = qualified_model("blocked-entry-champion", -0.5, 1)
    database.save_learning_model(champion)
    learner = LearningEngine(database, settings)
    learner._activate_model(champion)
    learner.mode = LearningMode.ACTIVE
    now = datetime.now(UTC) - timedelta(hours=8)
    for index in range(30):
        mint = f"health-blocked-{index}"
        created_at = now + timedelta(minutes=10 * index)
        assert learner.register(make_decision(created_at, mint), make_state(mint), live=True)
        winner = make_state(mint)
        winner.virtual_quote_reserves = 45_000_000_000
        learner.observe_market(winner, created_at + timedelta(seconds=300), live=True)

    health = learner.active_model_health()
    assert learner.mode == LearningMode.ACTIVE
    assert health["state"] == "collecting"
    assert health["observed_count"] == 0
    database.close()


def test_healthy_active_model_promotes_only_after_unseen_monitoring(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    champion = qualified_model("healthy-champion", 0.5, 1)
    database.save_learning_model(champion)
    learner = LearningEngine(database, settings)
    history_time = datetime.now(UTC) - timedelta(days=2)
    for index in range(50):
        mint = f"promotion-history-{index}"
        created_at = history_time + timedelta(minutes=10 * index)
        assert learner.register(make_decision(created_at, mint), make_state(mint), live=True)
        learner.observations[mint].checkpoints["300"] = LearningCheckpoint(
            horizon_seconds=300,
            observed_at=created_at + timedelta(seconds=300),
            net_return=0.1,
            exit_value_lamports=1_100_000,
        )
    learner._activate_model(champion)
    learner.mode = LearningMode.ACTIVE
    challenger = qualified_model("newer-challenger", 0.4, 10)
    learner.models.append(challenger)
    database.save_learning_model(challenger)
    now = datetime.now(UTC) - timedelta(hours=8)

    for index in range(29):
        mint = f"health-promote-{index}"
        created_at = now + timedelta(minutes=10 * index)
        assert learner.register(
            make_decision(created_at, mint),
            make_state(mint),
            live=True,
            evaluation_actionable=True,
        )
        winner = make_state(mint)
        winner.virtual_quote_reserves = 45_000_000_000
        learner.observe_market(winner, created_at + timedelta(seconds=300), live=True)

    assert learner.active_model is not None
    assert learner.active_model.version == champion.version

    final_mint = "health-promote-29"
    final_time = now + timedelta(minutes=290)
    assert learner.register(
        make_decision(final_time, final_mint),
        make_state(final_mint),
        live=True,
        evaluation_actionable=True,
    )
    final_winner = make_state(final_mint)
    final_winner.virtual_quote_reserves = 45_000_000_000
    learner.observe_market(final_winner, final_time + timedelta(seconds=300), live=True)

    assert learner.active_model is not None
    assert learner.active_model.version == challenger.version
    assert learner.active_model_health()["state"] == "collecting"
    database.close()


def test_active_learner_returns_to_shadow_when_risk_or_configuration_changes(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    fingerprint = ["config-a"]
    model = qualified_model("context-bound", 0.2, 80).model_copy(
        update={"configuration_fingerprint": "config-a"}
    )
    database.save_learning_model(model)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: fingerprint[0])
    learner._activate_model(model)
    learner.mode = LearningMode.ACTIVE

    # A drawdown-only season boundary calls set_risk_mode with the same personality. It must not
    # deactivate the compatible Challenger or create a false new learning cohort.
    learner.set_risk_mode(RiskMode.BALANCED)
    assert learner.mode == LearningMode.ACTIVE
    assert learner.active_model is not None
    assert learner.active_model.version == model.version

    learner.set_risk_mode(RiskMode.SAFE)
    assert learner.mode == LearningMode.SHADOW
    assert learner.active_model is None

    learner.current_risk_mode = RiskMode.BALANCED
    learner._activate_model(model)
    learner.mode = LearningMode.ACTIVE
    fingerprint[0] = "config-b"
    learner.configuration_changed()
    assert learner.mode == LearningMode.SHADOW
    assert learner.active_model is None
    database.close()


def test_qualified_challenger_can_only_veto_baseline_entries(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    configuration = "qualification-policy-journal"
    now = datetime.now(UTC) - timedelta(hours=2)
    for index in range(80):
        # Both chronological sections contain winners and losers. Qualification must prove the
        # exact deployed veto policy, not merely rank a validation tail containing only winners.
        opportunity = float(index % 2)
        decision = make_decision(now + timedelta(minutes=index), f"history-{index}", opportunity)
        observation = LearningObservation(
            observation_id=f"observation-{index}",
            decision_id=decision.decision_id,
            mint=decision.mint,
            symbol=decision.symbol,
            created_at=decision.created_at,
            baseline_action=DecisionAction.ENTER,
            baseline_actionable=True,
            risk_mode=RiskMode.BALANCED,
            baseline_edge_index=-opportunity,
            baseline_composite=decision.score.composite,
            features={
                "opportunity": opportunity,
                "danger": 0.1,
                "execution": 0.9,
                "confidence": 0.9,
                "buy_ratio": 0.7,
                "wallet_breadth": 10 / 30,
                "concentration": 0.12,
                "repetition": 0.1,
                "coordination": 0.1,
                "curve_progress": 0.4,
                "momentum": 0.2,
                "drawdown": 0.05,
                "reserve_depth": math.log1p(30) / math.log(1_001),
                "single_trade_wallet_ratio": 0.8,
                "round_trip_wallet_ratio": 0.1,
                "round_trip_volume_ratio": 0.15,
                "net_quote_flow_ratio": 0.6,
                "side_alternation_ratio": 0.4,
                "quantized_amount_repeat_ratio": 0.2,
                "slot_concentration_hhi": 0.1,
                "price_direction_consistency": 0.7,
                "microtrade_count_ratio": 0.1,
                "meaningful_volume_ratio": 0.9,
                "meaningful_wallet_ratio": 0.9,
                "median_trade_quote_sol": 0.03,
                "price_path_efficiency": 0.65,
                "rapid_price_reversal_ratio": 0.2,
                "trade_density_5m": 0.05,
            },
            token_units=1,
            entry_cost_lamports=1_000_000,
            entry_price_impact_fraction=0.001,
            fee_bps=125,
            checkpoints={
                "300": LearningCheckpoint(
                    horizon_seconds=300,
                    observed_at=decision.created_at + timedelta(seconds=300),
                    net_return=opportunity - 0.5,
                    exit_value_lamports=max(0, int((opportunity + 0.5) * 1_000_000)),
                )
            },
            status=LearningObservationStatus.COMPLETE,
            season_id=f"season-{index}",
            configuration_fingerprint=configuration,
            baseline_version=BASELINE_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
        )
        database.save_learning_observation(observation)
        checkpoint = observation.checkpoints["300"]
        database.save_learning_evidence_episode(
            LearningEvidenceEpisode(
                episode_id=f"policy-{index}",
                idempotency_key=f"policy-{index}",
                evidence_schema_version=LEARNING_EVIDENCE_SCHEMA_VERSION,
                lane=LearningEvidenceLane.POLICY,
                status=LearningEvidenceStatus.COMPLETE,
                trajectory_key=f"proof-trajectory-{index}",
                mint=f"proof-{index}",
                symbol=observation.symbol,
                created_at=observation.created_at,
                entry_at=observation.created_at,
                completed_at=checkpoint.observed_at,
                source_mode="solana_mainnet",
                qualification_eligible=True,
                decision_id=f"proof-decision-{index}",
                season_id=observation.season_id,
                risk_mode=observation.risk_mode,
                configuration_fingerprint=configuration,
                baseline_version=BASELINE_VERSION,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                baseline_action=DecisionAction.ENTER,
                baseline_actionable=True,
                features=dict(observation.features),
                token_units=observation.token_units,
                entry_cost_lamports=observation.entry_cost_lamports,
                fee_bps=observation.fee_bps,
                checkpoints={"300": checkpoint.model_copy(deep=True)},
            )
        )

    learner = LearningEngine(
        database,
        settings,
        configuration_fingerprint=lambda: configuration,
    )
    final_now = now + timedelta(minutes=90)
    final_decision = make_decision(final_now, "history-final", 1.0).model_copy(
        update={"configuration_fingerprint": configuration, "season_id": "season-final"}
    )
    final_state = make_state("history-final")
    assert learner.register(
        final_decision,
        final_state,
        live=True,
        evaluation_actionable=True,
    )
    learner.observations["history-final"].checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=final_now + timedelta(seconds=300),
        net_return=0.5,
        exit_value_lamports=2_000_000,
    )
    learner.database.save_learning_observation(learner.observations["history-final"])
    resolve_policy_primary(
        learner,
        "history-final",
        final_now + timedelta(seconds=300),
        0.5,
    )
    learner._retrain_if_ready()  # noqa: SLF001 - force the public lifecycle's training boundary

    assert learner.latest_model is not None
    assert learner.latest_model.qualified is True
    assert learner.latest_model.embargoed_count == 4
    assert (
        learner.latest_model.training_count
        + learner.latest_model.embargoed_count
        + learner.latest_model.validation_count
        == learner.latest_model.sample_count
    )
    # The deployed artifact is the older-section candidate that earned validation, not a refit on
    # the held-out outcomes.
    assert learner.latest_model.policy_validation_count >= 20
    assert learner.latest_model.policy_veto_count >= 5
    assert learner.latest_model.policy_uplift_lower_bound is not None
    assert learner.latest_model.policy_uplift_lower_bound > 0
    learner.set_mode(LearningMode.ACTIVE)

    supported = learner.assess(
        make_decision(datetime.now(UTC), "high", 1.0).model_copy(
            update={"configuration_fingerprint": configuration}
        ),
        live=True,
    )
    assert supported.action == DecisionAction.ENTER
    assert supported.learning_assessment is not None
    assert supported.learning_assessment.applied is True

    cautioned = learner.assess(
        make_decision(datetime.now(UTC), "low", 0.0).model_copy(
            update={"configuration_fingerprint": configuration}
        ),
        live=True,
    )
    assert cautioned.action == DecisionAction.PASS
    assert "challenger_entry_veto" in cautioned.blockers

    unusual = make_decision(datetime.now(UTC), "unusual", 1.0).model_copy(
        update={"configuration_fingerprint": configuration}
    )
    unusual.feature_snapshot.values["wallet_volume_hhi"].value = 1.0
    assessed_unusual = learner.assess(unusual, live=True)
    assert assessed_unusual.action == DecisionAction.ENTER
    assert assessed_unusual.learning_assessment is not None
    assert assessed_unusual.learning_assessment.applied is False
    assert assessed_unusual.learning_assessment.verdict == "out_of_distribution"

    portfolio_blocked = learner.assess(
        make_decision(datetime.now(UTC), "portfolio-blocked", 0.0).model_copy(
            update={"configuration_fingerprint": configuration}
        ),
        live=True,
        baseline_actionable=False,
    )
    assert portfolio_blocked.action == DecisionAction.ENTER
    assert portfolio_blocked.learning_assessment is not None
    assert portfolio_blocked.learning_assessment.applied is False

    unsafe = make_decision(datetime.now(UTC), "unsafe", 1.0).model_copy(
        update={
            "action": DecisionAction.ABSTAIN,
            "configuration_fingerprint": configuration,
        }
    )
    assessed_unsafe = learner.assess(unsafe, live=True)
    assert assessed_unsafe.action == DecisionAction.ABSTAIN
    database.close()


def _supported_coach_hypothesis(now: datetime) -> CoachHypothesis:
    return CoachHypothesis(
        hypothesis_id="coach-supported-entry",
        signature="coach-supported-signature",
        coach_review_id="coach-review-supported",
        created_at=now,
        updated_at=now,
        cutoff_at=now,
        kind=CoachExperimentKind.ENTRY_VETO,
        skill=ChallengerSkill.ENTRY,
        state=CoachExperimentState.PROMISING,
        title="Preserve cash during weak momentum",
        rationale="Supported by independent forward evidence.",
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="coach-fp",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        dependency_versions={},
        model_name="qwen3.5:2b",
        conditions=[
            CoachCondition(feature_name="momentum", operator="<=", threshold=0),
        ],
        discovery_observed_count=80,
        discovery_usable_count=80,
        discovery_availability_fraction=1,
        discovery_mean_uplift=0.08,
        discovery_uplift_lower_bound=0.03,
        forward_observed_count=80,
        forward_usable_count=80,
        forward_availability_fraction=1,
        forward_season_count=2,
        forward_mean_uplift=0.07,
        forward_uplift_lower_bound=0.02,
        forward_uplift_upper_bound=0.12,
        resolved_at=now,
        resolution_reason="forward_proof_supported",
        contribution_state="ready",
    )


def _coach_test_champion(now: datetime) -> ChallengerSkillArtifact:
    return ChallengerSkillArtifact(
        version="challenger-skill-entry-existing-champion",
        skill=ChallengerSkill.ENTRY,
        created_at=now,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="coach-fp",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        outcomes_seen=100,
        sample_count=80,
        training_count=50,
        validation_count=30,
        feature_names=list(FEATURE_NAMES),
        parameters={
            "means": [0.0] * len(FEATURE_NAMES),
            "scales": [1.0] * len(FEATURE_NAMES),
            "coefficients": [0.2, *([0.0] * len(FEATURE_NAMES))],
        },
        metrics={"validation_rmse": 0.05},
        qualified=True,
    )


def test_supported_coach_policy_waits_for_an_existing_champion(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")

    version, result = learner.seed_coach_candidate(_supported_coach_hypothesis(datetime.now(UTC)))

    assert version is None
    assert result == "waiting_for_champion"
    assert learner.skill_artifacts == {}
    database.close()


def test_supported_coach_policy_enters_normal_tournament_without_activation(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    now = datetime.now(UTC)
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        "coach-fp",
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    champion = _coach_test_champion(now)
    learner._register_skill_artifact(champion, cohort_key)  # noqa: SLF001

    version, result = learner.seed_coach_candidate(_supported_coach_hypothesis(now))

    assert version is not None
    assert result == "handed_off"
    candidate = learner.skill_artifacts[version]
    state = learner.skill_states[(cohort_key, ChallengerSkill.ENTRY)]
    assert state.champion_version == champion.version
    assert state.testing_version == candidate.version
    assert learner.active_skill_versions == {}
    assert _predict_skill_artifact(candidate, {"momentum": -0.1}) == -1
    assert _predict_skill_artifact(candidate, {"momentum": 0.1}) == 1
    assert learner.seed_coach_candidate(_supported_coach_hypothesis(now)) == (
        version,
        "handed_off",
    )
    database.close()


def test_coach_tournament_candidate_retires_when_ensemble_context_changes(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    now = datetime.now(UTC)
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        "coach-fp",
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    champion = _coach_test_champion(now)
    learner._register_skill_artifact(champion, cohort_key)  # noqa: SLF001
    version, result = learner.seed_coach_candidate(_supported_coach_hypothesis(now))
    assert version is not None and result == "handed_off"

    learner.active_skill_versions = {ChallengerSkill.ENTRY.value: champion.version}
    learner._advance_entry_tournaments()  # noqa: SLF001

    state = learner.skill_states[(cohort_key, ChallengerSkill.ENTRY)]
    assert state.champion_version == champion.version
    assert state.testing_version is None
    assert version in state.rejected_versions
    assert state.last_tournament["result"] == "context_stale"
    database.close()


def test_coach_handoff_rejects_policy_outside_deterministic_allowlist(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    now = datetime.now(UTC)
    cohort_key = _challenger_cohort_key(
        RiskMode.BALANCED,
        "coach-fp",
        BASELINE_VERSION,
        FEATURE_SCHEMA_VERSION,
    )
    assert cohort_key is not None
    champion = _coach_test_champion(now)
    learner._register_skill_artifact(champion, cohort_key)  # noqa: SLF001
    malformed = _supported_coach_hypothesis(now).model_copy(
        update={
            "conditions": [
                CoachCondition(
                    feature_name="opportunity",
                    operator=">=",
                    threshold=0.1,
                )
            ]
        }
    )

    assert learner.seed_coach_candidate(malformed) == (None, "coach_context_stale")
    state = learner.skill_states[(cohort_key, ChallengerSkill.ENTRY)]
    assert state.champion_version == champion.version
    assert state.testing_version is None
    database.close()


def test_coach_context_outcome_clock_survives_restart_and_pruning(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    now = datetime.now(UTC)
    decision = make_decision(now, "coach-clock").model_copy(
        update={
            "model_version": BASELINE_VERSION,
            "configuration_fingerprint": "coach-fp",
        }
    )
    assert learner.register(decision, make_state("coach-clock"), live=True)
    observation = learner.observations["coach-clock"]
    observation.checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=now + timedelta(seconds=300),
        net_return=0.05,
        exit_value_lamports=observation.entry_cost_lamports + 1,
    )
    observation.status = LearningObservationStatus.COMPLETE
    database.save_learning_observation(observation)
    database.close()

    restarted_database = Database(settings.database_path)
    restarted = LearningEngine(
        restarted_database,
        settings,
        configuration_fingerprint=lambda: "coach-fp",
    )
    assert (
        restarted.context_outcomes_seen(
            RiskMode.BALANCED,
            "coach-fp",
            BASELINE_VERSION,
            FEATURE_SCHEMA_VERSION,
            {},
        )
        == 1
    )
    context_key = next(iter(restarted.context_outcome_counts))
    restarted.context_outcome_counts[context_key] = 9
    restarted_database.set_setting(
        "learning_context_outcomes_seen",
        restarted.context_outcome_counts,
    )
    restarted_database.prune_learning_observations(0)
    restarted_database.close()

    pruned_database = Database(settings.database_path)
    pruned = LearningEngine(
        pruned_database,
        settings,
        configuration_fingerprint=lambda: "coach-fp",
    )
    assert (
        pruned.context_outcomes_seen(
            RiskMode.BALANCED,
            "coach-fp",
            BASELINE_VERSION,
            FEATURE_SCHEMA_VERSION,
            {},
        )
        == 9
    )
    pruned_database.close()
