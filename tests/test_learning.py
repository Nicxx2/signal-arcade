from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.features import TokenState
from signal_arcade.intelligence.learning import FEATURE_NAMES, LearningEngine
from signal_arcade.models import (
    DataValue,
    Decision,
    DecisionAction,
    DecisionScore,
    FeatureSnapshot,
    LearningCheckpoint,
    LearningMode,
    LearningModel,
    LearningObservation,
    LearningObservationStatus,
    RiskMode,
)
from signal_arcade.paper.curve_math import quote_buy, quote_sell


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


def qualified_model(version: str, prediction: float, outcomes_seen: int) -> LearningModel:
    return LearningModel(
        version=f"learner-v4-{version}",
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
        policy_veto_count=5,
        policy_winner_veto_count=0,
        policy_mean_uplift=0.05,
        policy_uplift_lower_bound=0.01,
        qualified=True,
    )


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
    assert learner.observe_market(improved, now + timedelta(seconds=60), live=True) == 1
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
    assert learner.observe_market(improved, now + timedelta(seconds=300), live=True) == 1
    assert learner.observe_market(improved, now + timedelta(seconds=600), live=True) == 1
    assert learner.observe_market(improved, now + timedelta(seconds=900), live=True) == 1
    assert learner.observe_market(improved, now + timedelta(seconds=1_200), live=True) == 1
    observation = learner.observations["mint-live"]
    assert observation.status == LearningObservationStatus.COMPLETE
    assert learner.has_pending_mint("mint-live") is False
    assert observation.checkpoints["300"].net_return is not None
    assert database.list_learning_observations()[0].status == LearningObservationStatus.COMPLETE
    database.reset_paper_state()
    assert len(database.list_learning_observations()) == 1
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
    ["learner-v1-80-legacy", "learner-v3-80-pre-integrity"],
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
    now = datetime.now(UTC) - timedelta(hours=2)
    for index in range(79):
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
        )
        database.save_learning_observation(observation)

    learner = LearningEngine(database, settings)
    final_now = now + timedelta(minutes=90)
    final_decision = make_decision(final_now, "history-final", 1.0)
    final_state = make_state("history-final")
    assert learner.register(final_decision, final_state, live=True)
    learner.observations["history-final"].checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=final_now + timedelta(seconds=300),
        net_return=0.5,
        exit_value_lamports=2_000_000,
    )
    learner.database.save_learning_observation(learner.observations["history-final"])
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

    supported = learner.assess(make_decision(datetime.now(UTC), "high", 1.0), live=True)
    assert supported.action == DecisionAction.ENTER
    assert supported.learning_assessment is not None
    assert supported.learning_assessment.applied is True

    cautioned = learner.assess(make_decision(datetime.now(UTC), "low", 0.0), live=True)
    assert cautioned.action == DecisionAction.PASS
    assert "learner_conservative_return_not_positive" in cautioned.blockers

    unusual = make_decision(datetime.now(UTC), "unusual", 1.0)
    unusual.feature_snapshot.values["wallet_volume_hhi"].value = 1.0
    assessed_unusual = learner.assess(unusual, live=True)
    assert assessed_unusual.action == DecisionAction.ENTER
    assert assessed_unusual.learning_assessment is not None
    assert assessed_unusual.learning_assessment.applied is False
    assert assessed_unusual.learning_assessment.verdict == "out_of_distribution"

    portfolio_blocked = learner.assess(
        make_decision(datetime.now(UTC), "portfolio-blocked", 0.0),
        live=True,
        baseline_actionable=False,
    )
    assert portfolio_blocked.action == DecisionAction.ENTER
    assert portfolio_blocked.learning_assessment is not None
    assert portfolio_blocked.learning_assessment.applied is False

    unsafe = make_decision(datetime.now(UTC), "unsafe", 1.0).model_copy(
        update={"action": DecisionAction.ABSTAIN}
    )
    assessed_unsafe = learner.assess(unsafe, live=True)
    assert assessed_unsafe.action == DecisionAction.ABSTAIN
    database.close()
