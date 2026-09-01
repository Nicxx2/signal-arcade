from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import (
    RISK_LIMITS,
    ChallengerEvaluationReceipt,
    ChallengerSkill,
    DataValue,
    Decision,
    DecisionAction,
    DecisionScore,
    EventKind,
    FeatureSnapshot,
    IntegrityAssessment,
    MarketIntegrityState,
    Position,
    QuoteCurrency,
    RiskMode,
    SizingAssessment,
)
from signal_arcade.paper.broker import EQUITY_PEAK_BASIS, PaperBroker
from signal_arcade.strategy import (
    BASELINE_VERSION,
    INTEGRITY_POLICY_VERSION,
    PREVIOUS_BASELINE_VERSION,
    PREVIOUS_INTEGRITY_POLICY_VERSION,
    RECENT_BASELINE_VERSION,
    RECENT_INTEGRITY_POLICY_VERSION,
    SIZING_POLICY_VERSION,
)


def make_features(now: datetime, mint: str = "mint") -> FeatureSnapshot:
    return FeatureSnapshot(
        mint=mint,
        symbol="TEST",
        name="Test",
        venue="pump_curve",
        computed_at=now,
        values={
            "creator_sells_5m": DataValue(
                value=0,
                unit="count",
                as_of=now,
                sources=["test"],
                freshness_seconds=0,
                quality=1,
            )
        },
        data_confidence=1,
    )


def make_integrity_features(
    now: datetime,
    *,
    severe: bool,
    mint: str = "mint",
) -> FeatureSnapshot:
    snapshot = make_features(now, mint)
    values = {
        "age_seconds": 45,
        "trade_count_5m": 30,
        "round_trip_wallet_ratio": 0.9 if severe else 0.0,
        "round_trip_volume_ratio": 0.95 if severe else 0.0,
        "net_quote_flow_ratio": 0.02 if severe else 0.8,
        "side_alternation_ratio": 0.96 if severe else 0.2,
        "quantized_amount_repeat_ratio": 0.9 if severe else 0.1,
        "slot_concentration_hhi": 0.75 if severe else 0.08,
        "price_direction_consistency": 0.99 if severe else 0.55,
        "multi_trade_signature_ratio": 0.7 if severe else 0.0,
        "microtrade_count_ratio": 0.95 if severe else 0.10,
        "meaningful_volume_ratio": 0.10 if severe else 0.90,
        "meaningful_wallet_ratio": 0.10 if severe else 0.90,
        "median_trade_quote_sol": 0.002 if severe else 0.03,
        "price_path_efficiency": 0.05 if severe else 0.65,
        "rapid_price_reversal_ratio": 0.90 if severe else 0.20,
        "trade_density_5m": 0.95 if severe else 0.05,
    }
    for name, value in values.items():
        snapshot.values[name] = DataValue(
            value=value,
            unit="fraction",
            as_of=now,
            sources=["test"],
            freshness_seconds=0,
            quality=1,
        )
    snapshot.values["integrity_window_complete"] = DataValue(
        value=True,
        unit="boolean",
        as_of=now,
        sources=["test"],
        freshness_seconds=0,
        quality=1,
    )
    return snapshot


def make_decision(
    now: datetime,
    mint: str = "mint",
    risk_mode: RiskMode = RiskMode.BALANCED,
) -> Decision:
    features = make_features(now, mint)
    return Decision(
        decision_id=f"decision-{mint}",
        mint=mint,
        symbol="TEST",
        created_at=now,
        action=DecisionAction.ENTER,
        risk_mode=risk_mode,
        score=DecisionScore(
            opportunity=0.8,
            danger=0.1,
            execution=0.9,
            confidence=0.9,
            net_edge_index=0.1,
            composite=80,
        ),
        reasons=["test"],
        blockers=[],
        feature_snapshot=features,
    )


def make_current_decision(now: datetime, mint: str) -> Decision:
    decision = make_decision(now, mint)
    decision.model_version = BASELINE_VERSION
    decision.planned_order_size_sol = 0.025
    decision.integrity_assessment = IntegrityAssessment(
        policy_version=INTEGRITY_POLICY_VERSION,
        state=MarketIntegrityState.CLEAN,
        score=0,
        coverage=1,
        sample_count=30,
        category_count=0,
        evidence=["clean sample"],
    )
    decision.sizing_assessment = SizingAssessment(
        policy_version=SIZING_POLICY_VERSION,
        base_size_sol=0.025,
        desired_size_sol=0.025,
        selected_size_sol=0.025,
        account_allocation_fraction=0.0025,
    )
    return decision


def make_broker(database: Database, settings) -> PaperBroker:  # type: ignore[no-untyped-def]
    broker = PaperBroker(database, settings)
    if not broker.initialized:
        broker.initialize(QuoteCurrency.SOL, 10_000_000_000)
    return broker


def test_order_fills_only_on_eligible_future_state(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    state = TokenState(
        mint="mint",
        name="Test",
        symbol="TEST",
        created_at=now - timedelta(seconds=30),
        last_event_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert (
        broker.on_market_state(
            state=state,
            features=make_features(now),
            event_kind=EventKind.MARKET,
            source_event_id="liquidity-event",
            now=now + timedelta(milliseconds=1),
            mode=RiskMode.BALANCED,
        )
        == []
    )
    assert order.order_id in broker.pending
    receipts = broker.on_market_state(
        state=state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="future-event",
        now=now + timedelta(milliseconds=2),
        mode=RiskMode.BALANCED,
    )
    assert len(receipts) == 1
    assert receipts[0].source_event_id == "future-event"
    assert broker.cash_lamports < broker.starting_lamports
    assert "mint" in broker.positions
    assert database.ledger_balance("cash") == broker.cash_lamports
    position = broker.positions.pop("mint")
    database.delete_position(position.position_id)
    assert broker.submit_decision(make_decision(now + timedelta(seconds=30))) is None
    database.close()


def test_pending_order_recovers_after_restart(settings) -> None:  # type: ignore[no-untyped-def]
    settings.entry_latency_ms = 10_000
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    assert broker.submit_decision(make_decision(datetime.now(UTC))) is not None
    assert len(broker.pending) == 1
    recovered = PaperBroker(database, settings)
    assert len(recovered.pending) == 1
    assert next(iter(recovered.pending.values())).reserved_account_minor > 0
    portfolio = recovered.snapshot()
    assert portfolio.reserved_cash_lamports > 0
    assert portfolio.available_cash_lamports == (
        portfolio.cash_lamports - portfolio.reserved_cash_lamports
    )
    database.close()


def test_realized_profit_returns_to_cash_and_scales_cautiously(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    starting = broker.cash_lamports
    assert broker.submit_decision(make_decision(now)) is not None
    entry_state = TokenState(
        mint="mint",
        symbol="TEST",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.on_market_state(
        state=entry_state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )

    profitable_state = TokenState(
        mint="mint",
        symbol="TEST",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=60_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    receipts = broker.on_market_state(
        state=profitable_state,
        features=make_features(now + timedelta(seconds=10)),
        event_kind=EventKind.TRADE,
        source_event_id="profitable-exit",
        now=now + timedelta(seconds=10),
        mode=RiskMode.BALANCED,
    )
    assert len(receipts) == 1
    assert receipts[0].side.value == "sell"
    assert receipts[0].exit_assessment is not None
    assert receipts[0].exit_assessment.reason == "take_profit"
    assert receipts[0].position_opened_at is not None
    assert receipts[0].entry_risk_mode == RiskMode.BALANCED
    assert receipts[0].peak_account_minor > 0
    assert receipts[0].realized_return_fraction is not None
    assert receipts[0].peak_return_fraction is not None
    persisted_sell = database.list_fills()[0]
    assert persisted_sell.fill_id == receipts[0].fill_id
    assert persisted_sell.exit_assessment == receipts[0].exit_assessment
    assert persisted_sell.peak_account_minor == receipts[0].peak_account_minor
    portfolio = broker.snapshot()
    assert portfolio.positions == []
    assert portfolio.realized_pnl_lamports > 0
    assert portfolio.cash_lamports == starting + portfolio.realized_pnl_lamports
    assert portfolio.equity_lamports == portfolio.cash_lamports
    assert 0.025 < broker.planned_order_size_sol(RiskMode.BALANCED) <= 0.0375
    database.close()


def test_manual_profile_exit_uses_a_real_fill_without_policy_credit(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    state = TokenState(
        mint="manual-exit",
        symbol="REAL",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.submit_decision(make_decision(now, "manual-exit")) is not None
    assert broker.on_market_state(
        state=state,
        features=make_features(now, "manual-exit"),
        event_kind=EventKind.TRADE,
        source_event_id="real-entry-state",
        now=now,
        mode=RiskMode.BALANCED,
    )
    assert broker.schedule_profile_transition_exits(now + timedelta(seconds=1)) == 1

    receipts = broker.process_due_orders(
        state=state,
        features=make_features(now + timedelta(seconds=2), "manual-exit"),
        source_event_id="real-manual-exit-state",
        now=now + timedelta(seconds=2),
        mode=RiskMode.BALANCED,
    )

    assert len(receipts) == 1
    assert receipts[0].side.value == "sell"
    assert receipts[0].exit_assessment is None
    assert "scheduled_reason:manual_profile_change" in receipts[0].assumptions
    assert receipts[0].source_event_id == "real-manual-exit-state"
    assert broker.positions == {}
    assert database.list_fills()[0].fill_id == receipts[0].fill_id
    database.close()


def test_pending_buys_reserve_position_capacity(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)

    for index in range(4):
        order, blocker = broker.submit_decision_with_reason(make_decision(now, f"mint-{index}"))
        assert order is not None
        assert blocker is None

    order, blocker = broker.submit_decision_with_reason(make_decision(now, "mint-overflow"))
    assert order is None
    assert blocker == "portfolio_capacity_reached"
    assert len(broker.pending) == 4
    database.close()


def test_pending_buy_is_rejected_if_drawdown_limit_is_crossed_before_fill(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    starting_cash = broker.cash_lamports
    database.set_setting("peak_equity_lamports", int(starting_cash * 1.2))
    database.set_setting("equity_peak_basis", EQUITY_PEAK_BASIS)
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )

    receipts = broker.process_due_orders(
        state=state,
        features=make_features(now),
        source_event_id="drawdown-crossed",
        now=order.fill_after + timedelta(milliseconds=1),
        mode=RiskMode.BALANCED,
    )

    assert receipts == []
    assert broker.cash_lamports == starting_cash
    assert order.order_id not in broker.pending
    failed = database.list_orders()[0]
    assert failed.status.value == "failed"
    assert failed.failure_reason == "fill_rejected:portfolio_drawdown_limit_reached"
    assert broker.snapshot(RiskMode.BALANCED).risk_halted is True
    database.close()


def test_drawdown_halt_never_blocks_an_existing_position_exit(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    entry_state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.on_market_state(
        state=entry_state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="entry-before-halt",
        now=now,
        mode=RiskMode.BALANCED,
    )
    database.set_setting("peak_equity_lamports", broker.starting_lamports * 2)
    database.set_setting("equity_peak_basis", EQUITY_PEAK_BASIS)
    assert broker.snapshot(RiskMode.BALANCED).risk_halted is True
    profitable_state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now + timedelta(seconds=10),
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=60_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )

    receipts = broker.on_market_state(
        state=profitable_state,
        features=make_features(now + timedelta(seconds=10)),
        event_kind=EventKind.TRADE,
        source_event_id="exit-during-halt",
        now=now + timedelta(seconds=10),
        mode=RiskMode.BALANCED,
    )

    assert len(receipts) == 1
    assert receipts[0].side.value == "sell"
    assert "mint" not in broker.positions
    database.close()


def test_dormant_positions_do_not_permanently_consume_trading_capacity(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)

    for index in range(RISK_LIMITS[RiskMode.BALANCED].max_open_positions):
        mint = f"dormant-{index}"
        order = broker.submit_decision(make_decision(now, mint))
        assert order is not None
        fill_at = order.fill_after + timedelta(milliseconds=1)
        state = TokenState(
            mint=mint,
            symbol="TEST",
            last_event_at=fill_at,
            last_event_id=f"entry-{index}",
            virtual_token_reserves=1_073_000_000_000_000,
            virtual_quote_reserves=30_000_000_000,
            real_token_reserves=793_100_000_000_000,
        )
        assert broker.process_due_orders(
            state=state,
            features=make_features(fill_at, mint),
            source_event_id=state.last_event_id,
            now=fill_at,
            mode=RiskMode.BALANCED,
        )
        broker.positions[mint].last_marked_at = now - timedelta(
            seconds=settings.position_mark_stale_seconds + 1
        )

    portfolio = broker.snapshot(RiskMode.BALANCED)
    assert portfolio.stale_position_count == RISK_LIMITS[RiskMode.BALANCED].max_open_positions
    assert portfolio.risk_halted is False

    order, blocker = broker.submit_decision_with_reason(make_decision(now, "fresh-opportunity"))

    assert order is not None
    assert blocker is None
    database.close()


def test_fill_rechecks_capacity_after_risk_mode_is_reduced(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    mints = ["mint-a", "mint-b", "mint-c"]
    for mint in mints:
        assert broker.submit_decision(make_decision(now, mint, RiskMode.AGGRESSIVE)) is not None

    for index, mint in enumerate(mints):
        state = TokenState(
            mint=mint,
            name="Test",
            symbol="TEST",
            created_at=now - timedelta(seconds=30),
            last_event_at=now,
            virtual_token_reserves=1_073_000_000_000_000,
            virtual_quote_reserves=30_000_000_000,
            real_token_reserves=793_100_000_000_000,
        )
        receipts = broker.on_market_state(
            state=state,
            features=make_features(now, mint),
            event_kind=EventKind.TRADE,
            source_event_id=f"future-event-{index}",
            now=now + timedelta(milliseconds=index + 1),
            mode=RiskMode.SAFE,
        )
        assert len(receipts) == (1 if index < 2 else 0)

    assert len(broker.positions) == 2
    failed = [order for order in database.list_orders() if order.status.value == "failed"]
    assert len(failed) == 1
    assert failed[0].failure_reason == "fill_rejected:portfolio_capacity_reached"
    database.close()


def test_pending_order_expires_even_without_another_market_event(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    expired = broker.expire_stuck_orders(order.fill_after + timedelta(seconds=91))
    assert [item.order_id for item in expired] == [order.order_id]
    assert not broker.pending
    saved = database.list_orders()
    assert saved[0].status.value == "failed"
    assert saved[0].failure_reason == "no_fresh_executable_market_state_within_90_seconds"
    database.close()


def test_elapsed_order_uses_latest_fresh_reserves_without_waiting_for_another_trade(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    settings.entry_latency_ms = 850
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        last_event_id="observed-entry-state",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )

    receipts = broker.process_due_orders(
        state=state,
        features=make_features(order.fill_after),
        source_event_id=state.last_event_id,
        now=order.fill_after + timedelta(milliseconds=1),
        mode=RiskMode.BALANCED,
    )

    assert len(receipts) == 1
    assert receipts[0].source_event_id == "observed-entry-state"
    assert "filled_after_configured_latency_against_latest_observed_reserves" in (
        receipts[0].assumptions
    )
    assert order.order_id not in broker.pending
    database.close()


def test_stale_position_mark_is_separated_from_conservative_equity(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        last_event_id="entry",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.process_due_orders(
        state=state,
        features=make_features(now),
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    stored = broker.positions["mint"]
    stored.last_marked_at = now - timedelta(seconds=settings.position_mark_stale_seconds + 1)

    portfolio = broker.snapshot(RiskMode.BALANCED)

    assert portfolio.stale_position_count == 1
    assert portfolio.invested_value_lamports == 0
    assert portfolio.stale_invested_value_lamports == stored.last_mark_lamports
    assert portfolio.last_known_equity_lamports > portfolio.equity_lamports
    assert portfolio.positions[0].mark_is_stale is True
    database.close()


def test_legacy_unverified_equity_peak_is_rebased_to_trustworthy_cash(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    database.set_setting("peak_equity_lamports", broker.starting_lamports * 2)
    database.set_setting("equity_peak_basis", None)

    portfolio = broker.snapshot(RiskMode.BALANCED)

    assert portfolio.drawdown_fraction == 0
    assert portfolio.risk_halted is False
    assert database.get_setting("peak_equity_lamports") == broker.starting_lamports
    assert database.get_setting("equity_peak_basis") == "executable-route-v1"
    database.close()


def test_peak_migration_preserves_a_genuine_recorded_cash_high(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    genuine_peak = int(broker.starting_lamports * 1.2)
    database.record_equity(genuine_peak, genuine_peak)
    database.set_setting("peak_equity_lamports", broker.starting_lamports * 2)
    database.set_setting("equity_peak_basis", None)

    portfolio = broker.snapshot(RiskMode.BALANCED)

    assert portfolio.drawdown_fraction == pytest.approx(1 / 6)
    assert portfolio.risk_halted is True
    assert database.get_setting("peak_equity_lamports") == genuine_peak
    database.close()


def test_route_blocked_indication_cannot_inflate_executable_equity(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        last_event_id="entry",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.process_due_orders(
        state=state,
        features=make_features(now),
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    state.last_event_at = now + timedelta(seconds=1)
    blocked = make_features(state.last_event_at).model_copy(
        update={"hard_flags": ["pumpswap_route_unverified"]}
    )
    broker.observe_market_state(state=state, features=blocked, now=state.last_event_at)

    portfolio = broker.snapshot(RiskMode.BALANCED)

    assert portfolio.invested_value_lamports == 0
    assert portfolio.route_blocked_position_count == 1
    assert portfolio.route_blocked_invested_value_lamports > 0
    assert portfolio.excluded_invested_value_lamports == (
        portfolio.route_blocked_invested_value_lamports
    )
    assert portfolio.positions[0].market_status == "exit_blocked"
    assert portfolio.positions[0].mark_is_executable is False
    assert portfolio.last_known_equity_lamports > portfolio.equity_lamports
    database.close()


def test_exact_empty_quote_vault_cannot_create_an_executable_paper_mark(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        last_event_id="entry",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.process_due_orders(
        state=state,
        features=make_features(now),
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    prior_mark = broker.positions["mint"].last_mark_lamports
    state.real_quote_reserves = 0

    position = broker.positions["mint"]
    position.opened_at = now - timedelta(days=1)
    broker.reassess_position(
        state=state,
        features=make_features(now + timedelta(seconds=1)),
        now=now + timedelta(seconds=1),
        mode=RiskMode.BALANCED,
    )

    position = broker.positions["mint"]
    assert position.last_mark_lamports == prior_mark
    assert position.mark_is_executable is False
    assert position.market_status == "exit_blocked"
    assert "insufficient_real_quote_liquidity" in position.mark_blockers
    assert position.exit_assessment is not None
    assert position.exit_assessment.action == "exit"
    assert broker.pending == {}
    database.close()


def test_heartbeat_reassessment_never_refreshes_stale_reserves(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        last_event_id="entry",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.process_due_orders(
        state=state,
        features=make_features(now),
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    original_marked_at = broker.positions["mint"].last_marked_at
    heartbeat_at = now + timedelta(seconds=settings.position_mark_stale_seconds + 5)
    stale_features = make_features(heartbeat_at).model_copy(
        update={"hard_flags": ["stale_market_data"]}
    )

    broker.reassess_position(
        state=state,
        features=stale_features,
        now=heartbeat_at,
        mode=RiskMode.BALANCED,
    )

    position = broker.positions["mint"]
    assert position.last_marked_at == original_marked_at
    assert position.mark_is_executable is False
    assert position.mark_is_stale is True
    assert position.market_status == "dormant"
    assert broker.pending == {}
    database.close()


def test_fill_database_failure_rolls_back_every_accounting_effect(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    state = TokenState(
        mint="mint",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    database._conn.executescript(  # noqa: SLF001 - intentional storage fault injection
        """
        CREATE TRIGGER reject_test_position BEFORE INSERT ON positions
        BEGIN SELECT RAISE(ABORT, 'injected position failure'); END;
        """
    )
    starting_cash = broker.cash_lamports
    with pytest.raises(sqlite3.IntegrityError, match="injected position failure"):
        broker.on_market_state(
            state=state,
            features=make_features(now),
            event_kind=EventKind.TRADE,
            source_event_id="future-event",
            now=now + timedelta(milliseconds=1),
            mode=RiskMode.BALANCED,
        )
    assert broker.cash_lamports == starting_cash
    assert order.order_id in broker.pending
    assert database.list_orders()[0].status.value == "pending"
    assert database.list_fills() == []
    assert database.list_positions() == []
    database.close()


def test_pending_buy_does_not_fill_after_curve_route_becomes_unconfirmed(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    state = TokenState(
        mint="mint",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
        complete=True,
    )
    unsafe_features = make_features(now).model_copy(
        update={"hard_flags": ["curve_complete_route_unconfirmed"]}
    )
    receipts = broker.on_market_state(
        state=state,
        features=unsafe_features,
        event_kind=EventKind.TRADE,
        source_event_id="complete-event",
        now=now + timedelta(seconds=1),
        mode=RiskMode.BALANCED,
    )
    assert receipts == []
    assert order.order_id in broker.pending
    assert database.list_fills() == []
    database.close()


def test_fresh_broker_is_unfunded_until_user_initializes_it(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = PaperBroker(database, settings)

    assert broker.initialized is False
    assert broker.snapshot().cash_lamports == 0
    assert broker.submit_decision(make_decision(datetime.now(UTC))) is None

    broker.initialize(QuoteCurrency.SOL, 2_500_000_000)
    assert broker.snapshot().initialized is True
    assert broker.cash_lamports == 2_500_000_000
    with pytest.raises(ValueError, match="already initialized"):
        broker.initialize(QuoteCurrency.USDC, 1_000_000_000)
    database.close()


def test_usdc_accounting_converts_fill_costs_at_observed_sol_price(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = PaperBroker(database, settings)
    broker.initialize(QuoteCurrency.USDC, 1_000_000_000)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is None
    order = broker.submit_decision(make_decision(now), sol_usd_price=150.0)
    assert order is not None
    state = TokenState(
        mint="mint",
        name="Test",
        symbol="TEST",
        created_at=now - timedelta(seconds=30),
        last_event_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )

    receipts = broker.on_market_state(
        state=state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="future-event",
        now=now + timedelta(milliseconds=1),
        mode=RiskMode.BALANCED,
        sol_usd_price=150.0,
    )

    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.account_currency == QuoteCurrency.USDC
    assert receipt.account_decimals == 6
    assert receipt.sol_usd_price == 150.0
    assert receipt.account_net_minor > 0
    assert broker.cash_lamports == 1_000_000_000 - receipt.account_net_minor
    assert broker.positions["mint"].entry_cost_lamports == receipt.account_net_minor
    database.close()


def test_usdc_entry_exposure_uses_usdc_minor_units(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = PaperBroker(database, settings)
    broker.initialize(QuoteCurrency.USDC, 100_000_000)  # 100 USDC

    order, blocker = broker.submit_decision_with_reason(
        make_decision(datetime.now(UTC)), sol_usd_price=150.0
    )

    assert blocker is None
    assert order is not None
    assert 3_000_000 < order.reserved_account_minor < 5_000_000
    database.close()


def test_clean_evidence_can_size_usdc_above_reference_inside_hard_caps(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = PaperBroker(database, settings)
    broker.initialize(QuoteCurrency.USDC, 1_000_000_000)  # 1,000 USDC
    now = datetime.now(UTC)
    decision = make_decision(now)
    decision.feature_snapshot.values["virtual_quote_reserve_sol"] = DataValue(
        value=30.0,
        unit="SOL",
        as_of=now,
        sources=["test"],
        freshness_seconds=0,
        quality=1,
    )
    decision.integrity_assessment = IntegrityAssessment(
        policy_version=INTEGRITY_POLICY_VERSION,
        state=MarketIntegrityState.CLEAN,
        score=0,
        coverage=1,
        sample_count=30,
        category_count=0,
        evidence=["clean sample"],
    )

    sizing = broker.plan_entry_size(decision, sol_usd_price=150.0)

    assert sizing.policy_version == SIZING_POLICY_VERSION
    assert sizing.selected_size_sol > sizing.base_size_sol
    assert sizing.selected_size_sol <= 0.20  # Balanced per-position cap is 3% = 30 USDC.
    assert 0.19 < sizing.maximum_size_sol <= 0.20
    assert sizing.selected_size_sol <= sizing.maximum_size_sol
    assert sizing.account_allocation_fraction <= 0.03
    assert sizing.constraints

    suspicious = decision.model_copy(deep=True)
    assert suspicious.integrity_assessment is not None
    suspicious.integrity_assessment.state = MarketIntegrityState.SUSPICIOUS
    suspicious.integrity_assessment.score = 0.7
    reduced = broker.plan_entry_size(suspicious, sol_usd_price=150.0)
    assert reduced.selected_size_sol < reduced.base_size_sol
    assert reduced.account_allocation_fraction < sizing.account_allocation_fraction

    concentrated = decision.model_copy(deep=True)
    assert concentrated.integrity_assessment is not None
    concentrated.integrity_assessment.state = MarketIntegrityState.UNCERTAIN
    concentrated.integrity_assessment.score = 0.8
    concentrated.integrity_assessment.category_count = 1
    concentrated.integrity_assessment.categories = ["concentrated_dispersion"]
    concentrated.model_version = BASELINE_VERSION
    reduced_uncertain = broker.plan_entry_size(concentrated, sol_usd_price=150.0)
    assert reduced_uncertain.selected_size_sol == pytest.approx(
        reduced_uncertain.base_size_sol * 0.70
    )
    assert reduced_uncertain.account_allocation_fraction < sizing.account_allocation_fraction

    # A locked v1.3 season retains its reference-size treatment for the same uncertainty.
    recent_concentrated = concentrated.model_copy(deep=True)
    recent_concentrated.model_version = RECENT_BASELINE_VERSION
    recent_reference = broker.plan_entry_size(recent_concentrated, sol_usd_price=150.0)
    assert recent_reference.selected_size_sol == pytest.approx(recent_reference.base_size_sol)
    database.close()


def test_current_baseline_pending_buy_revalidates_the_entry_thesis_before_fill(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    decision = make_current_decision(now, "fill-thesis")
    database.save_decision(decision)
    order = broker.submit_decision(decision)
    assert order is not None

    state = TokenState(
        mint="fill-thesis",
        symbol="TEST",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    receipts = broker.on_market_state(
        state=state,
        features=make_features(now, "fill-thesis"),
        event_kind=EventKind.TRADE,
        source_event_id="deteriorated-fill-state",
        now=now + timedelta(milliseconds=1),
        mode=RiskMode.BALANCED,
    )

    assert receipts == []
    assert order.order_id not in broker.pending
    persisted = next(item for item in database.list_orders() if item.order_id == order.order_id)
    assert persisted.failure_reason is not None
    assert persisted.failure_reason.startswith("fill_rejected:")
    assert "fill-thesis" not in broker.positions
    database.close()


def test_locked_previous_baseline_receipt_remains_fill_compatible(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    decision = make_current_decision(now, "previous-baseline-fill")
    decision.model_version = PREVIOUS_BASELINE_VERSION
    assert decision.integrity_assessment is not None
    decision.integrity_assessment.policy_version = PREVIOUS_INTEGRITY_POLICY_VERSION

    order, blocker = broker.submit_decision_with_reason(decision)
    assert blocker is None
    assert order is not None
    assert order.baseline_version_at_entry == PREVIOUS_BASELINE_VERSION

    evaluated_with: dict[str, object] = {}

    def evaluate(*args: object, **kwargs: object) -> Decision:
        evaluated_with.update(kwargs)
        return decision

    monkeypatch.setattr(broker._fill_decisions, "evaluate", evaluate)
    assert (
        broker._pending_buy_fill_blocker(
            order,
            RiskMode.BALANCED,
            None,
            make_features(now, decision.mint),
        )
        is None
    )
    assert evaluated_with["baseline_version"] == PREVIOUS_BASELINE_VERSION
    database.close()


def test_fill_rejects_reference_size_when_integrity_now_supports_only_reduced_size(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    decision = make_current_decision(now, "integrity-size-fill")
    order = broker.submit_decision(decision)
    assert order is not None

    refreshed = decision.model_copy(deep=True)
    refreshed.integrity_assessment = IntegrityAssessment(
        policy_version=INTEGRITY_POLICY_VERSION,
        state=MarketIntegrityState.SUSPICIOUS,
        score=0.7,
        coverage=1,
        sample_count=30,
        category_count=2,
        categories=["wallet_loops", "trade_structure"],
        evidence=["corroborated suspicious evidence"],
    )
    monkeypatch.setattr(broker._fill_decisions, "evaluate", lambda *args, **kwargs: refreshed)

    assert (
        broker._pending_buy_fill_blocker(
            order,
            RiskMode.BALANCED,
            None,
            make_features(now, "integrity-size-fill"),
        )
        == "entry_size_no_longer_supported_by_integrity"
    )

    reduced_decision = make_current_decision(now, "integrity-reduced-fill")
    assert reduced_decision.sizing_assessment is not None
    reduced_decision.planned_order_size_sol = 0.015
    reduced_decision.sizing_assessment.desired_size_sol = 0.015
    reduced_decision.sizing_assessment.selected_size_sol = 0.015
    reduced_decision.integrity_assessment = refreshed.integrity_assessment.model_copy(deep=True)
    reduced_order = broker.submit_decision(reduced_decision)
    assert reduced_order is not None
    refreshed_reduced = reduced_decision.model_copy(deep=True)
    monkeypatch.setattr(
        broker._fill_decisions,
        "evaluate",
        lambda *args, **kwargs: refreshed_reduced,
    )
    assert (
        broker._pending_buy_fill_blocker(
            reduced_order,
            RiskMode.BALANCED,
            None,
            make_features(now, "integrity-reduced-fill"),
        )
        is None
    )
    database.close()


def test_current_uncertain_size_is_rechecked_at_fill_without_rewriting_v13(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    uncertainty = IntegrityAssessment(
        policy_version=INTEGRITY_POLICY_VERSION,
        state=MarketIntegrityState.UNCERTAIN,
        score=0.70,
        coverage=1,
        sample_count=30,
        category_count=1,
        categories=["low_net_flow"],
        evidence=["isolated moderate warning"],
    )

    reference = make_current_decision(now, "uncertain-reference-fill")
    reference_order = broker.submit_decision(reference)
    assert reference_order is not None
    refreshed_reference = reference.model_copy(deep=True)
    refreshed_reference.integrity_assessment = uncertainty.model_copy(deep=True)
    monkeypatch.setattr(
        broker._fill_decisions,
        "evaluate",
        lambda *args, **kwargs: refreshed_reference,
    )
    assert (
        broker._pending_buy_fill_blocker(
            reference_order,
            RiskMode.BALANCED,
            None,
            make_features(now, reference.mint),
        )
        == "entry_size_no_longer_supported_by_integrity"
    )

    reduced = make_current_decision(now, "uncertain-reduced-fill")
    assert reduced.sizing_assessment is not None
    reduced.planned_order_size_sol = 0.0175
    reduced.sizing_assessment.desired_size_sol = 0.0175
    reduced.sizing_assessment.selected_size_sol = 0.0175
    reduced.integrity_assessment = uncertainty.model_copy(deep=True)
    reduced_order = broker.submit_decision(reduced)
    assert reduced_order is not None
    monkeypatch.setattr(broker._fill_decisions, "evaluate", lambda *args, **kwargs: reduced)
    assert (
        broker._pending_buy_fill_blocker(
            reduced_order,
            RiskMode.BALANCED,
            None,
            make_features(now, reduced.mint),
        )
        is None
    )

    recent = make_current_decision(now, "v13-uncertain-reference-fill")
    recent.model_version = RECENT_BASELINE_VERSION
    recent.integrity_assessment = uncertainty.model_copy(deep=True)
    recent.integrity_assessment.policy_version = RECENT_INTEGRITY_POLICY_VERSION
    recent_order = broker.submit_decision(recent)
    assert recent_order is not None
    monkeypatch.setattr(broker._fill_decisions, "evaluate", lambda *args, **kwargs: recent)
    assert (
        broker._pending_buy_fill_blocker(
            recent_order,
            RiskMode.BALANCED,
            None,
            make_features(now, recent.mint),
        )
        is None
    )
    database.close()


def test_entry_submission_fails_closed_for_unknown_or_incomplete_strategy_receipts(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)

    unknown = make_decision(now, "future-baseline")
    unknown.model_version = "baseline-v99"
    order, blocker = broker.submit_decision_with_reason(unknown)
    assert order is None
    assert blocker == "unsupported_baseline_version"

    incomplete = make_decision(now, "incomplete-baseline")
    incomplete.model_version = BASELINE_VERSION
    order, blocker = broker.submit_decision_with_reason(incomplete)
    assert order is None
    assert blocker == "current_baseline_receipt_incomplete"

    mismatched = make_current_decision(now, "mismatched-size")
    assert mismatched.sizing_assessment is not None
    mismatched.sizing_assessment.selected_size_sol = 0.02
    order, blocker = broker.submit_decision_with_reason(mismatched)
    assert order is None
    assert blocker == "current_baseline_size_receipt_mismatch"
    database.close()


def test_challenger_sizing_receipt_survives_submission_and_fill_revalidation(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)

    decision = make_current_decision(now, "challenger-sized")
    sizing_version = "challenger-skill-v1-sizing-fill-test"
    decision.model_version = f"{BASELINE_VERSION}+entry-test+{sizing_version}"
    decision.planned_order_size_sol = 0.05
    decision.challenger_assessments["sizing"] = ChallengerEvaluationReceipt(
        artifact_version=sizing_version,
        skill=ChallengerSkill.SIZING,
        evaluated_at=now,
        prediction=2.0,
        in_distribution=True,
        proposed_action="2",
        baseline_actionable=True,
        parameters={
            "applied": True,
            "selected_multiplier": 2.0,
            "baseline_size_sol": 0.025,
        },
    ).model_dump(mode="json")

    order, blocker = broker.submit_decision_with_reason(decision)
    assert blocker is None
    assert order is not None
    assert order.baseline_version_at_entry == BASELINE_VERSION
    monkeypatch.setattr(broker._fill_decisions, "evaluate", lambda *args, **kwargs: decision)
    assert (
        broker._pending_buy_fill_blocker(
            order,
            RiskMode.BALANCED,
            None,
            make_features(now, decision.mint),
        )
        is None
    )

    missing_receipt = make_current_decision(now, "challenger-size-missing")
    missing_receipt.model_version = f"{BASELINE_VERSION}+sizing-missing"
    missing_receipt.planned_order_size_sol = 0.05
    rejected, blocker = broker.submit_decision_with_reason(missing_receipt)
    assert rejected is None
    assert blocker == "current_baseline_size_receipt_mismatch"

    suspicious = make_current_decision(now, "challenger-size-suspicious")
    suspicious.model_version = f"{BASELINE_VERSION}+{sizing_version}"
    suspicious.planned_order_size_sol = 0.05
    assert suspicious.integrity_assessment is not None
    suspicious.integrity_assessment.state = MarketIntegrityState.SUSPICIOUS
    suspicious.challenger_assessments["sizing"] = decision.challenger_assessments["sizing"]
    rejected, blocker = broker.submit_decision_with_reason(suspicious)
    assert rejected is None
    assert blocker == "challenger_sizing_integrity_guard_failed"

    reduced = make_current_decision(now, "challenger-size-reduced")
    reduced.model_version = f"{BASELINE_VERSION}+sizing-reduced"
    reduced.planned_order_size_sol = 0.0125
    assert reduced.integrity_assessment is not None
    reduced.integrity_assessment.state = MarketIntegrityState.SUSPICIOUS
    reduced.challenger_assessments["sizing"] = ChallengerEvaluationReceipt(
        artifact_version="sizing-reduced",
        skill=ChallengerSkill.SIZING,
        evaluated_at=now,
        prediction=0.5,
        in_distribution=True,
        proposed_action="0.5",
        baseline_actionable=True,
        parameters={
            "applied": True,
            "selected_multiplier": 0.5,
            "baseline_size_sol": 0.025,
        },
    ).model_dump(mode="json")
    reduced_order, blocker = broker.submit_decision_with_reason(reduced)
    assert blocker is None
    assert reduced_order is not None
    database.close()


def test_integrity_exit_requires_persistence_and_clean_evidence_resets_it(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    position = Position(
        position_id="integrity-position",
        mint="mint",
        symbol="TEST",
        token_units=1,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=now - timedelta(seconds=30),
        entry_fill_id="integrity-fill",
        baseline_version_at_entry=BASELINE_VERSION,
    )
    broker.positions[position.mint] = position
    database.save_position(position)

    severe = make_integrity_features(now, severe=True)
    assert broker._persistent_integrity_exit_reason(position, severe, now) is None
    uncertain = severe.model_copy(deep=True)
    uncertain.values["trade_count_5m"].value = 10
    assert (
        broker._persistent_integrity_exit_reason(
            position,
            uncertain,
            now + timedelta(seconds=5),
        )
        is None
    )
    assert (
        broker._persistent_integrity_exit_reason(
            position,
            make_integrity_features(now + timedelta(seconds=70), severe=True),
            now + timedelta(seconds=70),
        )
        is None
    )
    assert position.integrity_warning_count == 1

    clean = make_integrity_features(now + timedelta(seconds=75), severe=False)
    assert (
        broker._persistent_integrity_exit_reason(
            position,
            clean,
            now + timedelta(seconds=75),
        )
        is None
    )
    assert position.integrity_warning_count == 0

    assert (
        broker._persistent_integrity_exit_reason(
            position,
            make_integrity_features(now + timedelta(seconds=80), severe=True),
            now + timedelta(seconds=80),
        )
        is None
    )
    assert (
        broker._persistent_integrity_exit_reason(
            position,
            make_integrity_features(now + timedelta(seconds=85), severe=True),
            now + timedelta(seconds=85),
        )
        is None
    )
    assert (
        broker._persistent_integrity_exit_reason(
            position,
            make_integrity_features(now + timedelta(seconds=90), severe=True),
            now + timedelta(seconds=90),
        )
        == "persistent_severe_market_integrity"
    )
    database.close()


def test_stopped_observation_preserves_position_then_resume_reassesses_it(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    entry_state = TokenState(
        mint="mint",
        name="Test",
        symbol="TEST",
        created_at=now - timedelta(seconds=30),
        last_event_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.on_market_state(
        state=entry_state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="entry-event",
        now=now + timedelta(milliseconds=1),
        mode=RiskMode.BALANCED,
    )
    low_state = TokenState(
        mint="mint",
        name="Test",
        symbol="TEST",
        created_at=entry_state.created_at,
        last_event_at=now + timedelta(seconds=5),
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=15_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )

    broker.observe_market_state(
        state=low_state,
        features=make_features(now + timedelta(seconds=5)),
        now=now + timedelta(seconds=5),
    )
    assert "mint" in broker.positions
    assert broker.positions["mint"].unrealized_pnl_lamports < 0
    assert broker.pending == {}

    broker.reassess_position(
        state=low_state,
        features=make_features(now + timedelta(seconds=5)),
        now=now + timedelta(seconds=5),
        mode=RiskMode.BALANCED,
    )
    assert len(broker.pending) == 1
    assert next(iter(broker.pending.values())).side.value == "sell"
    receipts = broker.on_market_state(
        state=low_state,
        features=make_features(now + timedelta(seconds=6)),
        event_kind=EventKind.TRADE,
        source_event_id="exit-event",
        now=now + timedelta(seconds=6),
        mode=RiskMode.BALANCED,
    )
    assert len(receipts) == 1
    assert "scheduled_reason:stop_loss" in receipts[0].assumptions
    assert "mint" not in broker.positions
    database.close()


def test_stopping_cancels_unfilled_orders_without_spending_cash(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    starting_cash = broker.cash_lamports

    assert broker.cancel_pending_orders(now) == 1
    assert broker.pending == {}
    assert broker.cash_lamports == starting_cash
    saved = database.list_orders()
    assert saved[0].status.value == "cancelled"
    assert saved[0].failure_reason == "paper_engine_stopped"
    database.close()


def test_failed_mint_safety_forces_an_exit_instead_of_trapping_the_position(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.on_market_state(
        state=state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )

    unsafe = make_features(now + timedelta(seconds=5)).model_copy(
        update={"hard_flags": ["mint_account_failed_safety_checks"]}
    )
    receipts = broker.on_market_state(
        state=state,
        features=unsafe,
        event_kind=EventKind.TRADE,
        source_event_id="unsafe-mint",
        now=now + timedelta(seconds=5),
        mode=RiskMode.BALANCED,
    )

    assert len(receipts) == 1
    assert "scheduled_reason:mint_safety_exit" in receipts[0].assumptions
    assert "mint" not in broker.positions
    database.close()


def test_peak_and_exit_policy_survive_restart(settings) -> None:  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    assert broker.submit_decision(make_decision(now)) is not None
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
    )
    assert broker.on_market_state(
        state=state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    state.virtual_quote_reserves = 33_000_000_000
    broker.reassess_position(
        state=state,
        features=make_features(now + timedelta(seconds=10)),
        now=now + timedelta(seconds=10),
        mode=RiskMode.BALANCED,
    )
    saved = broker.positions["mint"]
    assert saved.peak_mark_lamports >= saved.last_mark_lamports > 0
    assert saved.exit_assessment is not None

    recovered = PaperBroker(database, settings)

    assert recovered.positions["mint"].peak_mark_lamports == saved.peak_mark_lamports
    assert recovered.positions["mint"].exit_assessment == saved.exit_assessment
    assert recovered.positions["mint"].risk_mode_at_entry == RiskMode.BALANCED
    database.close()


def test_risk_slider_can_tighten_but_not_loosen_open_position() -> None:
    now = datetime.now(UTC)
    base = {
        "position_id": "position",
        "mint": "mint",
        "symbol": "TEST",
        "token_units": 1,
        "entry_cost_lamports": 100,
        "book_value_lamports": 100,
        "opened_at": now,
        "entry_fill_id": "fill",
    }
    entered_safe = Position(**base, risk_mode_at_entry=RiskMode.SAFE)
    entered_aggressive = Position(**base, risk_mode_at_entry=RiskMode.AGGRESSIVE)

    cannot_loosen = PaperBroker._effective_exit_limits(  # noqa: SLF001
        entered_safe, RiskMode.AGGRESSIVE
    )
    tightened = PaperBroker._effective_exit_limits(  # noqa: SLF001
        entered_aggressive, RiskMode.SAFE
    )

    assert cannot_loosen.stop_loss_fraction == RISK_LIMITS[RiskMode.SAFE].stop_loss_fraction
    assert cannot_loosen.hard_max_hold_seconds == RISK_LIMITS[RiskMode.SAFE].hard_max_hold_seconds
    assert tightened.stop_loss_fraction == RISK_LIMITS[RiskMode.SAFE].stop_loss_fraction
    assert tightened.hard_max_hold_seconds == RISK_LIMITS[RiskMode.SAFE].hard_max_hold_seconds
