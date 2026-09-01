from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from signal_arcade.intelligence.decision import DecisionEngine, assess_market_integrity
from signal_arcade.intelligence.features import FeatureEngine
from signal_arcade.models import (
    DataValue,
    DecisionAction,
    DecisionScore,
    EventKind,
    MarketEvent,
    MarketIntegrityState,
    RiskMode,
)
from signal_arcade.strategy import (
    BASELINE_VERSION,
    CORROBORATED_BASELINE_VERSION,
    INTEGRITY_POLICY_VERSION,
    LEGACY_BASELINE_VERSION,
    PREVIOUS_BASELINE_VERSION,
    PREVIOUS_INTEGRITY_POLICY_VERSION,
    RECENT_BASELINE_VERSION,
    RECENT_INTEGRITY_POLICY_VERSION,
)


def event(event_id: str, kind: EventKind, now: datetime, payload: dict[str, object]) -> MarketEvent:
    return MarketEvent(
        event_id=event_id,
        source="test",
        kind=kind,
        mint="Mint111111111111111111111111111111111111111",
        slot=int(event_id.strip("e") or 0),
        received_at=now,
        payload=payload,
    )


def _mark_integrity_window_complete(snapshot, now: datetime) -> None:  # type: ignore[no-untyped-def]
    snapshot.values["integrity_window_complete"] = DataValue(
        value=True,
        unit="boolean",
        as_of=now,
        sources=["test:event_pipeline"],
        freshness_seconds=0,
        quality=1,
    )


def test_synthetic_economic_activity_requires_corroboration_and_blocks_current_entry() -> None:
    now = datetime.now(UTC)
    start = now - timedelta(seconds=60)
    mint = "Mint111111111111111111111111111111111111111"
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            start,
            {
                "name": "Synthetic",
                "symbol": "SYN",
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    for index in range(30):
        engine.apply(
            event(
                f"e{index + 2}",
                EventKind.TRADE,
                now - timedelta(seconds=29 - index),
                {
                    "is_buy": index % 2 == 0,
                    "user": f"dust-wallet-{index}",
                    "sol_amount": 1_000_000,
                    "token_amount": 1_000_000_000 if index % 2 == 0 else 2_000_000_000,
                    "virtual_token_reserves": 1_000_000_000_000_000,
                    "virtual_sol_reserves": 30_000_000_000,
                    "real_token_reserves": 700_000_000_000_000,
                },
            )
        )
    snapshot = engine.snapshot(mint, now)
    assert snapshot is not None
    _mark_integrity_window_complete(snapshot, now)
    assert snapshot.values["microtrade_count_ratio"].value == 1
    assert snapshot.values["meaningful_volume_ratio"].value == 0
    assert snapshot.values["meaningful_wallet_ratio"].value == 0
    assert snapshot.values["median_trade_quote_sol"].value == pytest.approx(0.001)

    assessment = assess_market_integrity(snapshot)
    assert "synthetic_economic_activity" in assessment.categories
    assert "rapid_price_reversion" in assessment.categories
    assert assessment.state in {MarketIntegrityState.SUSPICIOUS, MarketIntegrityState.SEVERE}
    decision = DecisionEngine().evaluate(snapshot, RiskMode.AGGRESSIVE)
    assert decision.action == DecisionAction.PASS
    assert set(decision.blockers).intersection(
        {"market_integrity_suspicious", "market_integrity_severe"}
    )

    # A small median trade is a clue, not a verdict. With independent economic and path evidence
    # restored to ordinary values, that lone metric remains clean.
    isolated = snapshot.model_copy(deep=True)
    ordinary = {
        "wallet_volume_hhi": 0.05,
        "single_trade_wallet_ratio": 0.40,
        "round_trip_wallet_ratio": 0.0,
        "round_trip_volume_ratio": 0.0,
        "net_quote_flow_ratio": 0.80,
        "side_alternation_ratio": 0.20,
        "quantized_amount_repeat_ratio": 0.10,
        "slot_concentration_hhi": 0.05,
        "price_direction_consistency": 0.60,
        "multi_trade_signature_ratio": 0.0,
        "microtrade_count_ratio": 0.10,
        "meaningful_volume_ratio": 0.90,
        "meaningful_wallet_ratio": 0.90,
        "median_trade_quote_sol": 0.002,
        "price_path_efficiency": 0.60,
        "rapid_price_reversal_ratio": 0.20,
    }
    for name, value in ordinary.items():
        isolated.values[name].value = value
        isolated.values[name].quality = 1
        isolated.values[name].missing_reason = None
    isolated_assessment = assess_market_integrity(isolated)
    assert isolated_assessment.state == MarketIntegrityState.CLEAN
    assert isolated_assessment.category_count == 0

    missing_economic = isolated.model_copy(deep=True)
    missing_economic.values["meaningful_volume_ratio"].value = None
    missing_economic.values["meaningful_volume_ratio"].quality = 0
    missing_economic.values["meaningful_volume_ratio"].missing_reason = "test_missing"
    missing_decision = DecisionEngine().evaluate(missing_economic, RiskMode.AGGRESSIVE)
    assert missing_decision.integrity_assessment is not None
    assert missing_decision.integrity_assessment.state == MarketIntegrityState.UNCERTAIN
    assert "market_integrity_evidence_not_mature" in missing_decision.blockers


def test_integrity_window_and_venue_boundaries_fail_closed_only_for_current_policy() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    mint = "Mint111111111111111111111111111111111111111"
    for index in range(24):
        engine.apply(
            event(
                f"e{index + 1}",
                EventKind.TRADE,
                now - timedelta(seconds=40 - index),
                {
                    "is_buy": True,
                    "user": f"wallet-{index}",
                    "sol_amount": 30_000_000,
                    "token_amount": 1_000_000_000,
                    "virtual_token_reserves": 1_000_000_000_000_000,
                    "virtual_sol_reserves": 30_000_000_000,
                    "real_token_reserves": 700_000_000_000_000,
                },
            )
        )
    snapshot = engine.snapshot(mint, now)
    assert snapshot is not None
    snapshot.values["age_seconds"].value = 45
    snapshot.values["integrity_window_complete"] = DataValue(
        value=False,
        unit="boolean",
        as_of=now,
        sources=["test:event_pipeline"],
        freshness_seconds=0,
        quality=1,
        missing_reason="candidate_event_shed",
    )
    current = DecisionEngine().evaluate(snapshot, RiskMode.AGGRESSIVE)
    assert "market_integrity_evidence_not_mature" in current.blockers
    frozen = DecisionEngine().evaluate(
        snapshot,
        RiskMode.AGGRESSIVE,
        baseline_version=CORROBORATED_BASELINE_VERSION,
    )
    assert "market_integrity_evidence_not_mature" not in frozen.blockers

    amm_event = event(
        "e100",
        EventKind.TRADE,
        now + timedelta(seconds=2),
        {
            "event_name": "BuyEvent",
            "is_buy": True,
            "user": "amm-wallet",
            "quote_mint": "So11111111111111111111111111111111111111112",
            "pool": "Pool111111111111111111111111111111111111111",
            "pool_base_token_reserves": 2_000_000_000,
            "pool_quote_token_reserves": 4_000_000_000,
            "quote_amount_in": 20_000_000,
            "base_amount_out": 1_000_000_000,
        },
    ).model_copy(update={"source": "solana:pAMMBay6"})
    engine.apply(amm_event)
    migrated = engine.snapshot(mint, now + timedelta(seconds=3))
    assert migrated is not None
    assert migrated.venue == "pump_swap"
    assert migrated.values["trade_count_5m"].value == 1


def test_trade_window_cache_is_bounded_and_reports_live_buffer_saturation() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    mint = "Mint111111111111111111111111111111111111111"
    first = event(
        "e1",
        EventKind.TRADE,
        now,
        {
            "is_buy": True,
            "user": "one",
            "sol_amount": 20_000_000,
            "token_amount": 1_000_000_000,
            "virtual_token_reserves": 1_000_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
        },
    )
    engine.apply(first)
    initial = engine.snapshot(mint, now)
    assert initial is not None and initial.values["trade_count_5m"].value == 1
    engine.apply(
        first.model_copy(
            update={
                "event_id": "e2",
                "received_at": now + timedelta(milliseconds=100),
                "payload": {**first.payload, "user": "two"},
            }
        )
    )
    cached = engine.snapshot(mint, now + timedelta(milliseconds=100))
    refreshed = engine.snapshot(mint, now + timedelta(seconds=1, milliseconds=100))
    assert cached is not None and cached.values["trade_count_5m"].value == 1
    assert refreshed is not None and refreshed.values["trade_count_5m"].value == 2

    state = engine.tokens[mint]
    state.trades = deque(state.trades, maxlen=2)
    for index in range(3, 5):
        engine.apply(
            first.model_copy(
                update={
                    "event_id": f"e{index}",
                    "received_at": now + timedelta(seconds=index),
                    "payload": {**first.payload, "user": f"wallet-{index}"},
                }
            )
        )
    saturated = engine.snapshot(mint, now + timedelta(seconds=5))
    assert saturated is not None
    assert saturated.values["trade_buffer_saturated"].value is True


def test_position_rpc_refresh_updates_only_reserve_freshness() -> None:
    engine = FeatureEngine(stale_market_seconds=20)
    now = datetime.now(UTC)
    observed = now - timedelta(minutes=2)
    mint = "Mint111111111111111111111111111111111111111"
    curve = "Curve11111111111111111111111111111111111111"
    engine.apply(
        event(
            "e1",
            EventKind.TRADE,
            observed,
            {
                "bonding_curve": curve,
                "virtual_token_reserves": 1_000_000,
                "virtual_sol_reserves": 2_000_000,
                "real_token_reserves": 800_000,
                "is_buy": True,
            },
        )
    )

    assert engine.refresh_pump_curve(
        mint,
        curve_address=curve,
        values={
            "virtual_token_reserves": 900_000,
            "virtual_quote_reserves": 3_000_000,
            "real_token_reserves": 700_000,
            "real_quote_reserves": 2_000_000,
            "complete": False,
        },
        slot=2,
        at=now,
    )
    regular = engine.snapshot(mint, now)
    position = engine.position_snapshot(mint, now)
    assert regular is not None and "stale_market_data" in regular.hard_flags
    assert position is not None and "stale_market_data" not in position.hard_flags
    assert position.values["market_freshness"].value == 120
    assert position.values["reserve_freshness"].value == 0
    assert position.values["trade_count_5m"].value == 1
    assert position.values["price_sol"].sources == ["solana_rpc:position_watchdog"]
    assert engine.tokens[mint].real_quote_reserves == 2_000_000
    assert (
        engine.refresh_pump_curve(
            mint,
            curve_address=curve,
            values={
                "virtual_token_reserves": 850_000,
                "virtual_quote_reserves": 4_000_000,
                "real_token_reserves": 650_000,
                "real_quote_reserves": 3_000_000,
            },
            slot=2,
            at=now + timedelta(seconds=10),
        )
        is False
    )
    assert engine.tokens[mint].last_reserve_at == now
    assert engine.tokens[mint].virtual_quote_reserves == 3_000_000
    assert (
        engine.refresh_pump_curve(
            mint,
            curve_address="Wrong1111111111111111111111111111111111111",
            values={
                "virtual_token_reserves": 1,
                "virtual_quote_reserves": 1,
                "real_token_reserves": 1,
            },
            slot=3,
            at=now,
        )
        is False
    )
    assert (
        engine.refresh_pump_curve(
            mint,
            curve_address=curve,
            values={
                "virtual_token_reserves": 1,
                "virtual_quote_reserves": 1,
                "real_token_reserves": 1,
            },
            slot=0,
            at=now,
        )
        is False
    )


def test_missing_enrichment_is_unknown_not_zero() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now,
            {
                "name": "Test",
                "symbol": "TEST",
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    snapshot = engine.snapshot("Mint111111111111111111111111111111111111111", now)
    assert snapshot is not None
    assert snapshot.values["liquidity_usd"].value is None
    assert snapshot.values["liquidity_usd"].missing_reason


def test_stream_integrity_evidence_distinguishes_broad_buying_from_round_trips() -> None:
    now = datetime.now(UTC)
    mint = "Mint111111111111111111111111111111111111111"

    organic = FeatureEngine()
    organic.apply(
        event(
            "e1",
            EventKind.CREATE,
            now - timedelta(seconds=20),
            {
                "name": "Organic",
                "symbol": "ORG",
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    for index in range(10):
        trade = event(
            f"e{index + 2}",
            EventKind.TRADE,
            now - timedelta(seconds=10 - index),
            {
                "is_buy": True,
                "user": f"organic-wallet-{index}",
                "token_amount": 1_000_000,
                "sol_amount": 1_000_000 + index * 137_000,
            },
        ).model_copy(update={"signature": f"organic-signature-{index}"})
        organic.apply(trade)
    organic_snapshot = organic.snapshot(mint, now)
    assert organic_snapshot is not None
    assert organic_snapshot.number("single_trade_wallet_ratio") == 1.0
    assert organic_snapshot.number("round_trip_wallet_ratio") == 0.0
    assert organic_snapshot.number("round_trip_volume_ratio") == 0.0
    assert organic_snapshot.number("net_quote_flow_ratio") == 1.0
    assert organic_snapshot.number("side_alternation_ratio") == 0.0
    assert organic_snapshot.number("multi_trade_signature_ratio") == 0.0

    round_trips = FeatureEngine()
    round_trips.apply(
        event(
            "e1",
            EventKind.CREATE,
            now - timedelta(seconds=20),
            {
                "name": "Loop",
                "symbol": "LOOP",
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    for index in range(8):
        wallet = f"loop-wallet-{index // 2}"
        trade = event(
            f"e{index + 2}",
            EventKind.TRADE,
            now - timedelta(seconds=8 - index),
            {
                "is_buy": index % 2 == 0,
                "user": wallet,
                "token_amount": 1_000_000,
                "sol_amount": 2_000_000,
            },
        ).model_copy(update={"signature": f"loop-signature-{index // 2}"})
        round_trips.apply(trade)
    loop_snapshot = round_trips.snapshot(mint, now)
    assert loop_snapshot is not None
    assert loop_snapshot.number("single_trade_wallet_ratio") == 0.0
    assert loop_snapshot.number("round_trip_wallet_ratio") == 1.0
    assert loop_snapshot.number("round_trip_volume_ratio") == 1.0
    assert loop_snapshot.number("net_quote_flow_ratio") == 0.0
    assert loop_snapshot.number("side_alternation_ratio") == 1.0
    assert loop_snapshot.number("quantized_amount_repeat_ratio") == 1.0
    assert loop_snapshot.number("multi_trade_signature_ratio") == 1.0


def test_stream_integrity_missing_fields_remain_unknown() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    for index in range(8):
        engine.apply(
            event(
                f"e{index + 1}",
                EventKind.TRADE,
                now - timedelta(seconds=index),
                {
                    "is_buy": index % 2 == 0,
                    "token_amount": 1_000_000,
                },
            )
        )
    snapshot = engine.snapshot("Mint111111111111111111111111111111111111111", now)
    assert snapshot is not None
    assert snapshot.values["single_trade_wallet_ratio"].value is None
    assert snapshot.values["single_trade_wallet_ratio"].missing_reason
    assert snapshot.values["net_quote_flow_ratio"].value is None
    assert snapshot.values["net_quote_flow_ratio"].missing_reason
    assert snapshot.values["multi_trade_signature_ratio"].value is None
    assert snapshot.values["multi_trade_signature_ratio"].missing_reason


def test_future_timestamp_cannot_leak_into_point_in_time_evidence() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.TRADE,
            now + timedelta(seconds=1),
            {
                "is_buy": True,
                "user": "future-wallet",
                "token_amount": 1_000_000,
                "sol_amount": 1_000_000,
            },
        )
    )

    before = engine.snapshot("Mint111111111111111111111111111111111111111", now)
    after = engine.snapshot(
        "Mint111111111111111111111111111111111111111", now + timedelta(seconds=1)
    )
    assert before is not None and before.number("trade_count_5m") == 0
    assert before.values["single_trade_wallet_ratio"].value is None
    assert after is not None and after.number("trade_count_5m") == 1


def test_secondary_identity_is_display_only_and_never_overwrites_pump_identity() -> None:
    now = datetime.now(UTC)
    mint = "Mint111111111111111111111111111111111111111"
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now,
            {
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    before = engine.snapshot(mint, now)
    assert before is not None
    assert before.name == "Unknown token"
    assert before.symbol == "?"
    assert before.values["identity_source"].value == "unavailable"

    engine.add_enrichment(
        mint,
        {"base_token_name": "DEX Name", "base_token_symbol": "DEX"},
        now,
        source="dexscreener",
    )
    after = engine.snapshot(mint, now)
    assert after is not None
    assert after.name == "DEX Name"
    assert after.symbol == "DEX"
    assert after.values["identity_source"].value == "dexscreener"
    assert after.values["identity_source"].quality == 0.6
    assert after.data_confidence == before.data_confidence

    pump_engine = FeatureEngine()
    pump_engine.apply(
        event(
            "e2",
            EventKind.CREATE,
            now,
            {"name": "Pump Name", "symbol": "PUMP"},
        )
    )
    pump_engine.add_enrichment(
        mint,
        {"base_token_name": "Spoofed Name", "base_token_symbol": "SPOOF"},
        now,
        source="dexscreener",
    )
    authoritative = pump_engine.snapshot(mint, now)
    assert authoritative is not None
    assert authoritative.name == "Pump Name"
    assert authoritative.symbol == "PUMP"
    assert authoritative.values["identity_source"].value == "pump_create_event"


def test_snapshot_list_is_ordered_by_latest_market_activity() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    for mint, received_at in (
        ("OlderMint111111111111111111111111111111111", now - timedelta(minutes=2)),
        ("NewerMint111111111111111111111111111111111", now - timedelta(seconds=5)),
    ):
        engine.apply(
            MarketEvent(
                event_id=f"create-{mint}",
                source="test",
                kind=EventKind.CREATE,
                mint=mint,
                received_at=received_at,
                payload={"name": mint, "symbol": mint[:3]},
            )
        )

    snapshots = engine.list_snapshots(limit=2)
    assert [snapshot.mint for snapshot in snapshots] == [
        "NewerMint111111111111111111111111111111111",
        "OlderMint111111111111111111111111111111111",
    ]


def test_live_trade_updates_and_threaded_snapshots_do_not_race() -> None:
    now = datetime.now(UTC)
    mint = "Mint111111111111111111111111111111111111111"
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now,
            {
                "name": "Concurrent",
                "symbol": "LOCK",
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    for index in range(5_000):
        engine.apply(
            MarketEvent(
                event_id=f"warm-{index}",
                source="test",
                kind=EventKind.TRADE,
                mint=mint,
                slot=index + 2,
                received_at=now,
                payload={"is_buy": index % 2 == 0, "token_amount": 1_000_000},
            )
        )

    start = Event()

    def write_trades() -> None:
        start.wait()
        for index in range(1_000):
            engine.apply(
                MarketEvent(
                    event_id=f"live-{index}",
                    source="test",
                    kind=EventKind.TRADE,
                    mint=mint,
                    slot=index + 6_000,
                    received_at=now,
                    payload={"is_buy": True, "token_amount": 1_000_000},
                )
            )

    def read_snapshots() -> None:
        start.wait()
        for _ in range(100):
            snapshots = engine.list_snapshots(limit=1)
            assert snapshots and snapshots[0].mint == mint

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(write_trades)
        reader = pool.submit(read_snapshots)
        start.set()
        writer.result(timeout=20)
        reader.result(timeout=20)


def test_provider_freshness_is_tracked_independently() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now - timedelta(seconds=10),
            {
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    mint = "Mint111111111111111111111111111111111111111"
    engine.add_enrichment(
        mint,
        {"price_usd": 0.002, "price_native": 0.00001, "sol_usd_price": 200.0},
        now - timedelta(seconds=180),
        source="dexscreener",
    )
    engine.add_enrichment(
        mint,
        {"mint_safety": {"safe": True}},
        now,
        source="solana_rpc",
    )

    snapshot = engine.snapshot(mint, now)
    assert snapshot is not None
    assert snapshot.values["mint_safety_verified"].quality == 1
    assert snapshot.values["mint_safety_verified"].freshness_seconds == 0
    assert snapshot.values["sol_usd_price"].quality == 0
    assert snapshot.values["sol_usd_price"].freshness_seconds == 180
    assert snapshot.values["sol_usd_price"].missing_reason == "stale_enrichment"


def test_non_trade_amm_state_updates_reserves_without_refreshing_trade_freshness() -> None:
    now = datetime.now(UTC)
    mint = "Mint111111111111111111111111111111111111111"
    engine = FeatureEngine()
    state = engine.apply(
        MarketEvent(
            event_id="pool-create",
            source="solana:pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
            kind=EventKind.CREATE,
            mint=mint,
            received_at=now,
            payload={
                "event_name": "CreatePoolEvent",
                "base_mint": mint,
                "pool_base_amount": 1_000_000,
                "pool_quote_amount": 2_000_000,
            },
        )
    )
    assert state is not None
    assert state.virtual_token_reserves == 1_000_000
    assert state.virtual_quote_reserves == 2_000_000
    assert state.real_quote_reserves == 2_000_000

    engine.apply(
        MarketEvent(
            event_id="deposit",
            source="solana:pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
            kind=EventKind.MARKET,
            mint=mint,
            received_at=now + timedelta(seconds=5),
            payload={
                "event_name": "DepositEvent",
                "pool_base_token_reserves": 2_000_000,
                "pool_quote_token_reserves": 4_000_000,
            },
        )
    )
    assert state.virtual_token_reserves == 2_000_000
    assert state.virtual_quote_reserves == 4_000_000
    assert state.real_quote_reserves == 4_000_000
    assert state.last_event_at == now


def test_decision_progresses_from_watch_to_evaluated() -> None:
    start = datetime.now(UTC) - timedelta(seconds=30)
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            start,
            {
                "name": "Test",
                "symbol": "TEST",
                "creator": "creator",
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    for index in range(20):
        engine.apply(
            event(
                f"e{index + 2}",
                EventKind.TRADE,
                start + timedelta(seconds=index + 1),
                {
                    "event_name": "TradeEvent",
                    "is_buy": index % 5 != 0,
                    "user": f"wallet-{index % 12}",
                    "sol_amount": 30_000_000 + index * 1_000_000,
                    "token_amount": 1_000_000_000_000,
                    "virtual_token_reserves": 1_073_000_000_000_000 - index * 1_000_000_000_000,
                    "virtual_sol_reserves": 30_000_000_000 + index * 30_000_000,
                    "real_token_reserves": 793_100_000_000_000 - index * 1_000_000_000_000,
                },
            )
        )
    snapshot = engine.snapshot(
        "Mint111111111111111111111111111111111111111", start + timedelta(seconds=25)
    )
    assert snapshot is not None
    snapshot.values["integrity_window_complete"] = DataValue(
        value=True,
        unit="boolean",
        as_of=start + timedelta(seconds=25),
        sources=["test"],
        freshness_seconds=0,
        quality=1,
    )
    decision = DecisionEngine().evaluate(
        snapshot,
        RiskMode.AGGRESSIVE,
        baseline_version=LEGACY_BASELINE_VERSION,
    )
    assert decision.action in {DecisionAction.ENTER, DecisionAction.PASS}
    assert decision.score.confidence >= 0.55
    assert decision.model_version == LEGACY_BASELINE_VERSION

    # Integrity evidence is deliberately observational in v1.7. Extreme values must not alter
    # the fast baseline until a separately qualified learner is explicitly activated.
    extreme = snapshot.model_copy(deep=True)
    for name in (
        "single_trade_wallet_ratio",
        "round_trip_wallet_ratio",
        "round_trip_volume_ratio",
        "side_alternation_ratio",
        "quantized_amount_repeat_ratio",
        "slot_concentration_hhi",
        "price_direction_consistency",
    ):
        extreme.values[name].value = 1.0
    extreme.values["net_quote_flow_ratio"].value = 0.0
    extreme_decision = DecisionEngine().evaluate(
        extreme,
        RiskMode.AGGRESSIVE,
        baseline_version=LEGACY_BASELINE_VERSION,
    )
    assert extreme_decision.action == decision.action
    assert extreme_decision.score == decision.score
    assert extreme_decision.reasons == decision.reasons
    assert extreme_decision.blockers == decision.blockers

    # The current Baseline keeps that same short sample uncertain and waits for its integrity
    # evidence to mature. Extreme-looking values are not mislabeled as manipulation, but neither
    # are they treated as safe enough for an immediate entry.
    short_sample = DecisionEngine().evaluate(extreme, RiskMode.AGGRESSIVE)
    assert short_sample.model_version == BASELINE_VERSION
    assert short_sample.integrity_assessment is not None
    assert short_sample.integrity_assessment.state == MarketIntegrityState.UNCERTAIN
    assert "market_integrity_severe" not in short_sample.blockers
    assert "market_integrity_evidence_not_mature" in short_sample.blockers
    assert short_sample.action == DecisionAction.PASS

    # Seasons already locked to older Baselines keep their exact behavior after upgrade.
    recent_short_sample = DecisionEngine().evaluate(
        extreme,
        RiskMode.AGGRESSIVE,
        baseline_version=RECENT_BASELINE_VERSION,
    )
    assert "market_integrity_evidence_not_mature" not in recent_short_sample.blockers
    corroborated_short_sample = DecisionEngine().evaluate(
        extreme,
        RiskMode.AGGRESSIVE,
        baseline_version=CORROBORATED_BASELINE_VERSION,
    )
    assert "market_integrity_evidence_not_mature" not in corroborated_short_sample.blockers

    mature_extreme = extreme.model_copy(deep=True)
    mature_extreme.values["trade_count_5m"].value = 30
    mature_extreme.values["age_seconds"].value = 45
    current_decision = DecisionEngine().evaluate(mature_extreme, RiskMode.AGGRESSIVE)
    assert current_decision.integrity_assessment is not None
    assert current_decision.integrity_assessment.state == MarketIntegrityState.SEVERE
    assert current_decision.integrity_assessment.category_count >= 3
    assert "market_integrity_severe" in current_decision.blockers
    assert current_decision.action == DecisionAction.PASS

    incomplete = mature_extreme.model_copy(deep=True)
    for name in (
        "round_trip_wallet_ratio",
        "round_trip_volume_ratio",
        "side_alternation_ratio",
        "quantized_amount_repeat_ratio",
        "slot_concentration_hhi",
        "multi_trade_signature_ratio",
    ):
        incomplete.values[name].value = None
        incomplete.values[name].quality = 0
        incomplete.values[name].missing_reason = "test_missing"
    incomplete_decision = DecisionEngine().evaluate(incomplete, RiskMode.AGGRESSIVE)
    assert incomplete_decision.integrity_assessment is not None
    assert incomplete_decision.integrity_assessment.coverage < 0.75
    assert incomplete_decision.integrity_assessment.state == MarketIntegrityState.UNCERTAIN
    assert "market_integrity_evidence_not_mature" in incomplete_decision.blockers

    isolated = mature_extreme.model_copy(deep=True)
    isolated.values["round_trip_wallet_ratio"].value = 0.0
    isolated.values["round_trip_volume_ratio"].value = 0.0
    isolated.values["net_quote_flow_ratio"].value = 0.8
    isolated.values["side_alternation_ratio"].value = 0.2
    isolated.values["quantized_amount_repeat_ratio"].value = 0.1
    isolated.values["slot_concentration_hhi"].value = 0.08
    isolated.values["price_direction_consistency"].value = 1.0
    isolated_decision = DecisionEngine().evaluate(isolated, RiskMode.AGGRESSIVE)
    assert isolated_decision.integrity_assessment is not None
    assert isolated_decision.integrity_assessment.category_count == 1
    assert isolated_decision.integrity_assessment.state == MarketIntegrityState.UNCERTAIN
    assert "market_integrity_uncertain_high_risk" in isolated_decision.blockers
    assert isolated_decision.action == DecisionAction.PASS

    # The integrity boundary is a permanent Baseline safety rule, not a personality-specific
    # preference. Aggressive may accept more ordinary danger, but it cannot bypass unresolved
    # high-risk manipulation evidence; a recovered complete sample must also clear the earlier
    # provider-coverage maturity blocker deterministically.
    assert "market_integrity_evidence_not_mature" not in isolated_decision.blockers
    for mode in (RiskMode.SAFE, RiskMode.BALANCED, RiskMode.AGGRESSIVE):
        mode_decision = DecisionEngine().evaluate(isolated, mode)
        assert "market_integrity_uncertain_high_risk" in mode_decision.blockers
        assert mode_decision.action == DecisionAction.PASS

    exact_maturity = isolated.model_copy(deep=True)
    exact_maturity.values["trade_count_5m"].value = 24
    exact_maturity.values["age_seconds"].value = 30
    exact_maturity_decision = DecisionEngine().evaluate(exact_maturity, RiskMode.AGGRESSIVE)
    assert "market_integrity_evidence_not_mature" not in exact_maturity_decision.blockers
    for field, below in (("trade_count_5m", 23), ("age_seconds", 29.999)):
        below_maturity = exact_maturity.model_copy(deep=True)
        below_maturity.values[field].value = below
        below_decision = DecisionEngine().evaluate(below_maturity, RiskMode.AGGRESSIVE)
        assert "market_integrity_evidence_not_mature" in below_decision.blockers

    recent_isolated = DecisionEngine().evaluate(
        isolated,
        RiskMode.AGGRESSIVE,
        baseline_version=RECENT_BASELINE_VERSION,
    )
    assert recent_isolated.integrity_assessment is not None
    assert recent_isolated.integrity_assessment.policy_version == RECENT_INTEGRITY_POLICY_VERSION
    assert "market_integrity_uncertain_high_risk" not in recent_isolated.blockers

    moderate_isolated = isolated.model_copy(deep=True)
    moderate_isolated.values["price_direction_consistency"].value = 0.93
    moderate_decision = DecisionEngine().evaluate(moderate_isolated, RiskMode.AGGRESSIVE)
    assert moderate_decision.integrity_assessment is not None
    assert moderate_decision.integrity_assessment.state == MarketIntegrityState.UNCERTAIN
    assert 0 < moderate_decision.integrity_assessment.score < 0.80
    assert "market_integrity_uncertain_high_risk" not in moderate_decision.blockers

    isolated.values["price_direction_consistency"].value = 0.55
    clean_decision = DecisionEngine().evaluate(isolated, RiskMode.AGGRESSIVE)
    assert clean_decision.integrity_assessment is not None
    assert clean_decision.integrity_assessment.state == MarketIntegrityState.CLEAN

    # V2 treats extreme value concentration plus one-trade wallet dispersion as one independent
    # manipulation category. It prevents a size-up but cannot condemn the market by itself.
    concentrated_dispersion = isolated.model_copy(deep=True)
    concentrated_dispersion.values["wallet_volume_hhi"].value = 0.90
    concentrated_dispersion.values["single_trade_wallet_ratio"].value = 0.95
    dispersion_decision = DecisionEngine().evaluate(
        concentrated_dispersion,
        RiskMode.AGGRESSIVE,
    )
    assert dispersion_decision.integrity_assessment is not None
    assert dispersion_decision.integrity_assessment.policy_version == INTEGRITY_POLICY_VERSION
    assert dispersion_decision.integrity_assessment.categories == ["concentrated_dispersion"]
    assert dispersion_decision.integrity_assessment.state == MarketIntegrityState.UNCERTAIN
    assert "market_integrity_uncertain_high_risk" in dispersion_decision.blockers

    # The exact v1.2 generation remains frozen for already-locked seasons after an upgrade.
    previous_dispersion = DecisionEngine().evaluate(
        concentrated_dispersion,
        RiskMode.AGGRESSIVE,
        baseline_version=PREVIOUS_BASELINE_VERSION,
    )
    assert previous_dispersion.integrity_assessment is not None
    assert (
        previous_dispersion.integrity_assessment.policy_version == PREVIOUS_INTEGRITY_POLICY_VERSION
    )
    assert previous_dispersion.integrity_assessment.state == MarketIntegrityState.CLEAN

    # Either ingredient alone remains ordinary concentration/participation evidence. A second
    # independent category is still required before deterministic danger and sizing are reduced.
    lone_whale = concentrated_dispersion.model_copy(deep=True)
    lone_whale.values["single_trade_wallet_ratio"].value = 0.50
    lone_whale_decision = DecisionEngine().evaluate(lone_whale, RiskMode.AGGRESSIVE)
    assert lone_whale_decision.integrity_assessment is not None
    assert lone_whale_decision.integrity_assessment.state == MarketIntegrityState.CLEAN

    dispersed_organic = concentrated_dispersion.model_copy(deep=True)
    dispersed_organic.values["wallet_volume_hhi"].value = 0.10
    dispersed_organic_decision = DecisionEngine().evaluate(
        dispersed_organic,
        RiskMode.AGGRESSIVE,
    )
    assert dispersed_organic_decision.integrity_assessment is not None
    assert dispersed_organic_decision.integrity_assessment.state == MarketIntegrityState.CLEAN

    corroborated_dispersion = concentrated_dispersion.model_copy(deep=True)
    corroborated_dispersion.values["net_quote_flow_ratio"].value = 0.05
    corroborated_decision = DecisionEngine().evaluate(
        corroborated_dispersion,
        RiskMode.AGGRESSIVE,
    )
    assert corroborated_decision.integrity_assessment is not None
    assert set(corroborated_decision.integrity_assessment.categories) == {
        "concentrated_dispersion",
        "low_net_flow",
    }
    assert corroborated_decision.integrity_assessment.state == MarketIntegrityState.SUSPICIOUS

    with pytest.raises(ValueError, match="unsupported baseline version"):
        DecisionEngine().evaluate(
            isolated,
            RiskMode.AGGRESSIVE,
            baseline_version="baseline-future-unknown",
        )


def test_stale_data_forces_abstention() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now - timedelta(minutes=2),
            {
                "virtual_token_reserves": 1_000,
                "virtual_sol_reserves": 1_000,
                "real_token_reserves": 1_000,
            },
        )
    )
    snapshot = engine.snapshot("Mint111111111111111111111111111111111111111", now)
    assert snapshot is not None
    assert DecisionEngine().evaluate(snapshot, RiskMode.AGGRESSIVE).action == DecisionAction.ABSTAIN


def test_configured_stale_window_is_honoured() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine(stale_market_seconds=60)
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now - timedelta(seconds=30),
            {
                "virtual_token_reserves": 1_000,
                "virtual_sol_reserves": 1_000,
                "real_token_reserves": 1_000,
            },
        )
    )
    snapshot = engine.snapshot("Mint111111111111111111111111111111111111111", now)
    assert snapshot is not None
    assert "stale_market_data" not in snapshot.hard_flags


def test_pumpswap_uses_coin_creator_for_creator_sell_detection() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now,
            {
                "event_name": "CreatePoolEvent",
                "creator": "pool-creator",
                "coin_creator": "original-creator",
                "pool_base_token_reserves": 1_000_000,
                "pool_quote_token_reserves": 1_000_000,
            },
        )
    )
    engine.apply(
        event(
            "e2",
            EventKind.TRADE,
            now + timedelta(seconds=1),
            {
                "event_name": "SellEvent",
                "user": "original-creator",
                "base_amount_in": 1_000,
                "quote_amount_out": 1_000,
                "pool_base_token_reserves": 1_001_000,
                "pool_quote_token_reserves": 999_000,
            },
        )
    )
    snapshot = engine.snapshot(
        "Mint111111111111111111111111111111111111111", now + timedelta(seconds=1)
    )
    assert snapshot is not None
    assert "creator_sold_recently" in snapshot.hard_flags


def test_non_sol_quote_market_fails_closed() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now,
            {
                "virtual_token_reserves": 1_000_000,
                "virtual_quote_reserves": 1_000_000,
                "real_token_reserves": 1_000_000,
                "quote_mint": "USDC111111111111111111111111111111111111111",
            },
        )
    )
    snapshot = engine.snapshot("Mint111111111111111111111111111111111111111", now)
    assert snapshot is not None
    assert "unsupported_quote_mint_v1" in snapshot.hard_flags
    assert DecisionEngine().evaluate(snapshot, RiskMode.AGGRESSIVE).action == DecisionAction.ABSTAIN


def test_native_sol_quote_is_supported_on_pump_curve_only() -> None:
    now = datetime.now(UTC)
    mint = "Mint111111111111111111111111111111111111111"
    engine = FeatureEngine()
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now,
            {
                "virtual_token_reserves": 1_000_000,
                "virtual_sol_reserves": 1_000_000,
                "real_token_reserves": 1_000_000,
                "quote_mint": "11111111111111111111111111111111",
            },
        )
    )
    curve_snapshot = engine.snapshot(mint, now)
    assert curve_snapshot is not None
    assert "unsupported_quote_mint_v1" not in curve_snapshot.hard_flags

    engine.apply(
        event(
            "e2",
            EventKind.CREATE,
            now,
            {
                "event_name": "CreatePoolEvent",
                "pool": "Pool111111111111111111111111111111111111111",
                "quote_mint": "11111111111111111111111111111111",
                "pool_base_token_reserves": 1_000_000,
                "pool_quote_token_reserves": 1_000_000,
            },
        )
    )
    swap_snapshot = engine.snapshot(mint, now)
    assert swap_snapshot is not None
    assert "pumpswap_route_unverified" in swap_snapshot.hard_flags
    assert engine.confirm_pumpswap_route(
        mint,
        pool_address="Pool111111111111111111111111111111111111111",
        quote_mint="11111111111111111111111111111111",
    )
    swap_snapshot = engine.snapshot(mint, now)
    assert swap_snapshot is not None
    assert "unsupported_quote_mint_v1" in swap_snapshot.hard_flags


def test_verified_pumpswap_quote_is_pinned_until_the_pool_changes() -> None:
    now = datetime.now(UTC)
    mint = "Mint111111111111111111111111111111111111111"
    pool = "Pool111111111111111111111111111111111111111"
    next_pool = "NextPool11111111111111111111111111111111111"
    wrapped_sol = "So11111111111111111111111111111111111111112"
    claimed_quote = "USDC111111111111111111111111111111111111111"
    engine = FeatureEngine()
    state = engine.apply(
        event(
            "e501",
            EventKind.CREATE,
            now,
            {
                "event_name": "CreatePoolEvent",
                "pool": pool,
                "quote_mint": wrapped_sol,
                "pool_base_token_reserves": 1_000_000,
                "pool_quote_token_reserves": 1_000_000,
            },
        )
    )
    assert state is not None
    assert engine.confirm_pumpswap_route(
        mint,
        pool_address=pool,
        quote_mint=wrapped_sol,
    )

    engine.apply(
        event(
            "e502",
            EventKind.TRADE,
            now + timedelta(seconds=1),
            {
                "event_name": "BuyEvent",
                "pool": pool,
                "quote_mint": claimed_quote,
                "pool_base_token_reserves": 900_000,
                "pool_quote_token_reserves": 1_100_000,
            },
        )
    )
    assert state.route_verified is True
    assert state.quote_mint == wrapped_sol

    engine.apply(
        event(
            "e503",
            EventKind.TRADE,
            now + timedelta(seconds=2),
            {
                "event_name": "BuyEvent",
                "pool": next_pool,
                "quote_mint": claimed_quote,
                "pool_base_token_reserves": 800_000,
                "pool_quote_token_reserves": 1_200_000,
            },
        )
    )
    assert state.route_verified is False
    assert state.pool_address == next_pool
    assert state.quote_mint == claimed_quote


def test_pumpswap_fee_does_not_double_charge_buyback_or_cashback() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    mint = "Mint111111111111111111111111111111111111111"
    state = engine.apply(
        event(
            "e3",
            EventKind.TRADE,
            now,
            {
                "event_name": "SellEvent",
                "pool": "Pool111111111111111111111111111111111111111",
                "pool_base_token_reserves": 1_000_000,
                "pool_quote_token_reserves": 1_000_000,
                "lp_fee_basis_points": 20,
                "protocol_fee_basis_points": 5,
                "coin_creator_fee_basis_points": 5,
                "cashback_fee_basis_points": 100,
                "buyback_fee_basis_points": 5_000,
            },
        )
    )
    assert state is not None
    assert state.mint == mint
    assert state.fee_bps == 30


def test_net_edge_heuristic_accounts_for_observed_fees_and_network_cost() -> None:
    now = datetime.now(UTC)
    engine = FeatureEngine()
    mint = "Mint111111111111111111111111111111111111111"
    engine.apply(
        event(
            "e1",
            EventKind.CREATE,
            now - timedelta(seconds=30),
            {
                "virtual_token_reserves": 1_073_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_token_reserves": 793_100_000_000_000,
            },
        )
    )
    snapshot = engine.snapshot(mint, now - timedelta(seconds=30))
    assert snapshot is not None
    low_fee = DecisionEngine(one_way_network_fee_lamports=0).evaluate(snapshot, RiskMode.BALANCED)
    snapshot.values["observed_fee_bps"] = DataValue(
        value=500,
        unit="basis_points",
        as_of=now,
        sources=["test"],
        freshness_seconds=0,
        quality=1,
    )
    high_fee = DecisionEngine(one_way_network_fee_lamports=30_000).evaluate(
        snapshot, RiskMode.BALANCED
    )
    assert high_fee.score.net_edge_index < low_fee.score.net_edge_index


def test_legacy_expected_return_score_loads_without_preserving_misleading_name() -> None:
    score = DecisionScore.model_validate(
        {
            "opportunity": 0.6,
            "danger": 0.2,
            "execution": 0.9,
            "confidence": 0.8,
            "expected_net_return": 0.03,
            "composite": 72,
        }
    )

    assert score.net_edge_index == 0.03
    serialized = score.model_dump()
    assert serialized["net_edge_index"] == 0.03
    assert "expected_net_return" not in serialized
