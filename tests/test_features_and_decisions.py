from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

from signal_arcade.intelligence.decision import DecisionEngine
from signal_arcade.intelligence.features import FeatureEngine
from signal_arcade.models import (
    DataValue,
    DecisionAction,
    DecisionScore,
    EventKind,
    MarketEvent,
    RiskMode,
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
    decision = DecisionEngine().evaluate(snapshot, RiskMode.AGGRESSIVE)
    assert decision.action in {DecisionAction.ENTER, DecisionAction.PASS}
    assert decision.score.confidence >= 0.55
    assert decision.model_version == "baseline-v1.1"


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
