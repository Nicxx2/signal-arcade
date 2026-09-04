from __future__ import annotations

import asyncio
import json
import struct
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from signal_arcade.config import Settings
from signal_arcade.database import Database
from signal_arcade.intelligence.decision import INTEGRITY_MIN_AGE_SECONDS
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import (
    DataValue,
    Decision,
    DecisionAction,
    DecisionScore,
    EventKind,
    FeatureSnapshot,
    MarketEvent,
    PaperOrder,
    Position,
    QuoteCurrency,
    RiskMode,
)
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.provider_settings import ProviderConfiguration, ProviderPolicy
from signal_arcade.providers.anchor import b58encode
from signal_arcade.providers.demo import (
    DEMO_TICK_INTERVAL_SECONDS,
    DEMO_TICKS_PER_TOKEN,
    DemoFeed,
)
from signal_arcade.providers.http import SPL_TOKEN_PROGRAM
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM, PUMP_PROGRAM, SolanaLogProvider


def test_background_workers_recover_and_resolve_incidents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    enrichment_calls = 0
    heartbeat_calls = 0

    async def no_wait(_timeout: float) -> None:
        await asyncio.sleep(0)

    async def flaky_enrichment(_now: datetime) -> None:
        nonlocal enrichment_calls
        enrichment_calls += 1
        if enrichment_calls == 1:
            raise RuntimeError("temporary maintenance failure")
        orchestrator.stop_event.set()

    def flaky_heartbeat(
        _now: datetime,
    ) -> tuple[list[object], list[object], int, int]:
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if heartbeat_calls == 1:
            raise RuntimeError("temporary heartbeat failure")
        orchestrator.stop_event.set()
        return [], [], 0, 0

    async def exercise() -> None:
        monkeypatch.setattr(orchestrator, "_wait_for_stop", no_wait)
        monkeypatch.setattr(orchestrator, "_enrichment_tick", flaky_enrichment)
        await orchestrator._enrichment_loop()
        orchestrator.stop_event.clear()
        monkeypatch.setattr(orchestrator, "_heartbeat_tick", flaky_heartbeat)
        await orchestrator._heartbeat_loop()

    asyncio.run(exercise())

    assert enrichment_calls == 2
    assert heartbeat_calls == 2
    incidents = orchestrator.database.list_incidents(20)
    recovered = {
        incident.scope: incident for incident in incidents if incident.scope.endswith("_worker")
    }
    assert recovered["enrichment_worker"].resolved_at is not None
    assert recovered["heartbeat_worker"].resolved_at is not None
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_short_stream_reconnects_stay_out_of_current_status_and_coalesce(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))
    started = datetime(2026, 1, 1, tzinfo=UTC)

    async def exercise() -> None:
        await orchestrator._update_stream_incident(  # noqa: SLF001
            started,
            {"reconnects": 1, "connected": False, "last_error": "temporary"},
        )
        assert orchestrator.database.list_incidents() == []
        await orchestrator._update_stream_incident(  # noqa: SLF001
            started + timedelta(seconds=5),
            {"reconnects": 1, "connected": True, "last_error": None},
        )
        await orchestrator._update_stream_incident(  # noqa: SLF001
            started + timedelta(minutes=10),
            {"reconnects": 2, "connected": False, "last_error": "temporary again"},
        )
        await orchestrator._update_stream_incident(  # noqa: SLF001
            started + timedelta(minutes=10, seconds=4),
            {"reconnects": 2, "connected": True, "last_error": None},
        )
        await orchestrator.http.close()

    asyncio.run(exercise())

    incidents = orchestrator.database.list_incidents()
    assert len(incidents) == 1
    assert incidents[0].title == "Solana stream reconnected automatically"
    assert incidents[0].occurrences == 2
    assert incidents[0].resolved_at is not None
    orchestrator.database.close()


def test_sustained_stream_interruption_becomes_current_then_resolves(tmp_path: Path) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))
    started = datetime(2026, 1, 1, tzinfo=UTC)

    async def exercise() -> None:
        await orchestrator._update_stream_incident(  # noqa: SLF001
            started,
            {"reconnects": 1, "connected": False, "last_error": "still unavailable"},
        )
        await orchestrator._update_stream_incident(  # noqa: SLF001
            started + timedelta(seconds=16),
            {"reconnects": 1, "connected": False, "last_error": "still unavailable"},
        )
        current = orchestrator.database.list_incidents()
        assert len(current) == 1
        assert current[0].resolved_at is None
        await orchestrator._update_stream_incident(  # noqa: SLF001
            started + timedelta(seconds=20),
            {"reconnects": 1, "connected": True, "last_error": None},
        )
        await orchestrator.http.close()

    asyncio.run(exercise())

    assert orchestrator.database.list_incidents()[0].resolved_at is not None
    orchestrator.database.close()


def test_queue_pressure_uses_grace_and_quiet_period_before_status_changes(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))
    started = datetime(2026, 1, 1, tzinfo=UTC)

    async def exercise() -> None:
        orchestrator._note_queue_pressure(  # noqa: SLF001
            started,
            detail="brief burst",
            metadata={"dropped_total": 1},
        )
        await orchestrator._update_queue_incident(started + timedelta(seconds=11))  # noqa: SLF001
        recovered = orchestrator.database.list_incidents()
        assert len(recovered) == 1
        assert recovered[0].resolved_at is not None

        sustained_at = started + timedelta(minutes=2)
        orchestrator._note_queue_pressure(  # noqa: SLF001
            sustained_at,
            detail="sustained burst",
            metadata={"dropped_total": 2},
        )
        orchestrator._note_queue_pressure(  # noqa: SLF001
            sustained_at + timedelta(seconds=14),
            detail="sustained burst",
            metadata={"dropped_total": 3},
        )
        await orchestrator._update_queue_incident(  # noqa: SLF001
            sustained_at + timedelta(seconds=16)
        )
        current = [
            incident
            for incident in orchestrator.database.list_incidents()
            if incident.resolved_at is None
        ]
        assert len(current) == 1
        assert current[0].title == "Market event burst exceeded processing capacity"

        await orchestrator._update_queue_incident(  # noqa: SLF001
            sustained_at + timedelta(seconds=25)
        )
        assert all(
            incident.resolved_at is not None for incident in orchestrator.database.list_incidents()
        )
        await orchestrator.http.close()

    asyncio.run(exercise())
    orchestrator.database.close()


def test_rpc_error_redacts_credentials_and_query() -> None:
    url = "wss://rpc-user:rpc-password@rpc.example/ws?api-key=top-secret"
    resources = Path(__file__).parents[1] / "backend" / "signal_arcade" / "resources" / "idl"
    provider = SolanaLogProvider(url, resources)
    safe = provider._safe_error(RuntimeError(f"connection failed for {url}"))
    assert "rpc-password" not in safe
    assert "top-secret" not in safe
    assert "rpc.example" in safe


def test_solana_rate_limit_backoff_honors_retry_after_and_uses_long_cap() -> None:
    class Response:
        status_code = 429
        headers = {"Retry-After": "90"}

    class RateLimited(Exception):
        response = Response()

    assert SolanaLogProvider._retry_backoff(RateLimited("HTTP 429"), 1) == (90, 180)
    assert SolanaLogProvider._retry_backoff(RateLimited("HTTP 429"), 180) == (180, 300)


def test_solana_rate_limited_primary_activates_configured_public_fallback() -> None:
    resources = Path(__file__).parents[1] / "backend" / "signal_arcade" / "resources" / "idl"
    provider = SolanaLogProvider(
        "wss://keyed.example/?api-key=secret",
        resources,
        fallback_ws_url="wss://api.mainnet-beta.solana.com",
    )

    assert provider._activate_fallback(RuntimeError("server rejected connection: HTTP 429"))
    assert provider.active_ws_url == "wss://api.mainnet-beta.solana.com"
    assert provider.health()["fallback_active"] is True
    assert provider.health()["fallback_reason"] == "primary_rate_limited"


def test_solana_normal_reconnect_backoff_remains_short() -> None:
    assert SolanaLogProvider._retry_backoff(RuntimeError("temporary disconnect"), 8) == (8, 16)


def test_buffered_solana_burst_yields_to_http_and_health_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources = Path(__file__).parents[1] / "backend" / "signal_arcade" / "resources" / "idl"
    provider = SolanaLogProvider("wss://rpc.example", resources)
    mint = "Mint".ljust(32, "1")
    stop = asyncio.Event()
    probe_ran = False
    probe_seen_by_handler: list[bool] = []

    class FakeDecoder:
        def decode_log_line(
            self, line: str, expected_program: str | None = None
        ) -> tuple[str, str, dict[str, object]] | None:
            if line != "Program data: fixture":
                return None
            return (
                expected_program or PUMP_PROGRAM,
                "TradeEvent",
                {
                    "mint": mint,
                    "is_buy": True,
                },
            )

    provider.decoder = FakeDecoder()  # type: ignore[assignment]
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "result": 101},
        {"jsonrpc": "2.0", "id": 2, "result": 102},
    ]
    for index in range(3):
        messages.append(
            {
                "params": {
                    "result": {
                        "context": {"slot": index + 1},
                        "value": {
                            "err": None,
                            "signature": f"signature-{index}",
                            "logs": [
                                f"Program {PUMP_PROGRAM} invoke [1]",
                                "Program data: fixture",
                                f"Program {PUMP_PROGRAM} success",
                            ],
                        },
                    }
                }
            }
        )

    class FakeSocket:
        async def send(self, _message: str) -> None:
            return None

        async def recv(self) -> str:
            return json.dumps(messages.pop(0))

    class FakeConnection:
        async def __aenter__(self) -> FakeSocket:
            return FakeSocket()

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        "signal_arcade.providers.solana.websockets.connect",
        lambda *_args, **_kwargs: FakeConnection(),
    )

    async def probe() -> None:
        nonlocal probe_ran
        await asyncio.sleep(0)
        probe_ran = True

    async def handler(_event: MarketEvent) -> None:
        probe_seen_by_handler.append(probe_ran)
        if len(probe_seen_by_handler) == 3:
            stop.set()

    async def exercise() -> None:
        health_probe = asyncio.create_task(probe())
        await provider._run_once(handler, stop)  # noqa: SLF001
        await health_probe

    asyncio.run(exercise())

    assert provider.connected is True
    assert probe_seen_by_handler == [True, True, True]


def test_demo_sessions_do_not_reuse_persistent_event_ids() -> None:
    first = DemoFeed(seed=7)
    second = DemoFeed(seed=7)
    assert first.session_id != second.session_id


def test_demo_token_lifetime_can_clear_the_current_integrity_maturity_gate() -> None:
    observable_lifetime = (DEMO_TICKS_PER_TOKEN - 1) * DEMO_TICK_INTERVAL_SECONDS

    # A fill near the maturity boundary still receives a useful synthetic management window;
    # merely crossing the boundary would make the first position go dormant almost immediately.
    assert observable_lifetime >= INTEGRITY_MIN_AGE_SECONDS + 10


def test_pumpswap_pool_mapping_is_bounded_and_recent_entries_survive() -> None:
    resources = Path(__file__).parents[1] / "backend" / "signal_arcade" / "resources" / "idl"
    provider = SolanaLogProvider("wss://rpc.example", resources, max_pool_mappings=2)
    pools = [f"Pool{index}".ljust(32, "1") for index in range(3)]
    mints = [f"Mint{index}".ljust(32, "1") for index in range(3)]
    for pool, mint in zip(pools, mints, strict=True):
        provider.remember_pool_mapping({"pool": pool, "base_mint": mint})
    assert provider.mint_for_pool(pools[0]) is None
    assert provider.mint_for_pool(pools[1]) == mints[1]
    assert provider.mint_for_pool(pools[2]) == mints[2]


def test_pumpswap_pool_mapping_is_restored_from_persisted_events(tmp_path: Path) -> None:
    pool = "Pool".ljust(32, "1")
    mint = "Mint".ljust(32, "1")
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    database = Database(settings.database_path)
    database.append_event(
        MarketEvent(
            event_id="create-pool",
            source="solana:pump-amm",
            kind=EventKind.CREATE,
            mint=mint,
            received_at=datetime.now(UTC),
            payload={"event_name": "CreatePoolEvent", "pool": pool, "base_mint": mint},
        )
    )
    database.close()

    orchestrator = Orchestrator(settings)
    assert orchestrator.solana.mint_for_pool(pool) == mint
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_snapshot_exposes_server_timing_for_fresh_decision_views(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        demo_mode=True,
        candidate_window_minutes=17,
        stale_market_seconds=9,
        _env_file=None,
    )
    orchestrator = Orchestrator(settings)
    snapshot = orchestrator.snapshot()

    assert datetime.fromisoformat(snapshot["server_time"]).tzinfo is not None
    assert snapshot["candidate_window_minutes"] == 17
    assert snapshot["stale_market_seconds"] == 9
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_dashboard_reserves_positive_signals_and_uses_each_tokens_latest_state(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))
    now = datetime.now(UTC)

    def decision(
        decision_id: str,
        mint: str,
        action: DecisionAction,
        created_at: datetime,
    ) -> Decision:
        return Decision(
            decision_id=decision_id,
            mint=mint,
            symbol=mint.upper(),
            created_at=created_at,
            action=action,
            risk_mode=RiskMode.BALANCED,
            score=DecisionScore(
                opportunity=0.7,
                danger=0.1,
                execution=0.9,
                confidence=0.9,
                net_edge_index=0.04,
                composite=75,
            ),
            reasons=["test"],
            blockers=[],
            feature_snapshot=FeatureSnapshot(
                mint=mint,
                symbol=mint.upper(),
                name=mint,
                venue="test",
                computed_at=created_at,
                values={
                    "market_freshness": DataValue(
                        value=0,
                        unit="seconds",
                        as_of=created_at,
                        sources=["test"],
                        freshness_seconds=0,
                        quality=1,
                    )
                },
                data_confidence=0.9,
            ),
        )

    visible_watch = decision("watch-visible", "visible", DecisionAction.WATCH, now)
    superseded_watch = decision("watch-old", "changed", DecisionAction.WATCH, now)
    latest_pass = decision(
        "pass-new",
        "changed",
        DecisionAction.PASS,
        now + timedelta(milliseconds=1),
    )
    orchestrator.database.save_decision(visible_watch)
    orchestrator.database.save_decision(superseded_watch)
    orchestrator.database.save_decision(latest_pass)
    orchestrator.last_recorded_decision["visible"] = visible_watch
    orchestrator.last_recorded_decision["changed"] = latest_pass
    for index in range(60):
        noise = decision(
            f"noise-{index}",
            f"noise-{index}",
            DecisionAction.ABSTAIN,
            now + timedelta(seconds=1, milliseconds=index),
        )
        orchestrator.database.save_decision(noise)
        orchestrator.last_recorded_decision[noise.mint] = noise

    selected_ids = {item.decision_id for item in orchestrator._dashboard_decisions()}  # noqa: SLF001

    assert "watch-visible" in selected_ids
    assert "pass-new" in selected_ids
    assert "watch-old" not in selected_ids
    compact_watch = next(
        item
        for item in orchestrator.snapshot()["decisions"]
        if item["decision_id"] == "watch-visible"
    )
    assert compact_watch["feature_snapshot"]["values"]["market_freshness"]["value"] == 0
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_snapshot_view_stays_available_during_storage_maintenance(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    writer_owned = threading.Event()
    release_writer = threading.Event()

    def hold_maintenance_writer() -> None:
        with orchestrator.database._lock:  # noqa: SLF001 - simulate the cleanup writer
            writer_owned.set()
            release_writer.wait(timeout=5)

    worker = threading.Thread(target=hold_maintenance_writer)
    worker.start()
    assert writer_owned.wait(timeout=2)
    try:
        snapshot = asyncio.run(asyncio.wait_for(orchestrator.snapshot_view(), timeout=1))
        assert snapshot["database_ok"] is True
        assert snapshot["paper_only"] is True
    finally:
        release_writer.set()
        worker.join(timeout=2)
        asyncio.run(orchestrator.http.close())
        orchestrator.database.close()


def test_snapshot_cache_serves_last_complete_view_when_market_lock_is_busy(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))

    async def exercise() -> None:
        first = await orchestrator.snapshot_view()
        assert first["snapshot_generated_at"]
        orchestrator.invalidate_snapshot_cache()

        await orchestrator._event_lock.acquire()  # noqa: SLF001 - simulate a long market action
        started = time.monotonic()
        try:
            second = await orchestrator.snapshot_view()
        finally:
            orchestrator._event_lock.release()  # noqa: SLF001
        assert time.monotonic() - started < 1.25
        assert second["snapshot_generated_at"] == first["snapshot_generated_at"]
        assert second["snapshot_age_seconds"] >= first["snapshot_age_seconds"]
        await orchestrator.http.close()

    asyncio.run(exercise())
    orchestrator.database.close()


def test_snapshot_cache_stays_available_during_active_storage_maintenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))

    async def exercise() -> None:
        first = await orchestrator.snapshot_view()
        orchestrator.invalidate_snapshot_cache()
        orchestrator._storage_maintenance_active = True  # noqa: SLF001

        def fail_if_rebuilt() -> dict[str, object]:
            raise AssertionError("active maintenance must reuse the last complete dashboard")

        monkeypatch.setattr(orchestrator, "snapshot", fail_if_rebuilt)
        second = await orchestrator.snapshot_view()
        assert second["snapshot_generated_at"] == first["snapshot_generated_at"]
        assert second["snapshot_age_seconds"] >= first["snapshot_age_seconds"]
        await orchestrator.http.close()

    asyncio.run(exercise())
    orchestrator.database.close()


def test_storage_policy_save_defers_expensive_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    orchestrator._storage_maintenance_requested = False  # noqa: SLF001

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("interactive storage save must not run maintenance inline")

    monkeypatch.setattr(orchestrator.database, "prune_history", fail_if_called)
    monkeypatch.setattr(orchestrator.database, "enforce_storage_budget", fail_if_called)
    monkeypatch.setattr(orchestrator.database, "storage_stats", fail_if_called)

    max_bytes = 2 * 1024**3
    saved = asyncio.run(orchestrator.configure_storage(max_bytes, 12))

    assert saved["max_database_bytes"] == max_bytes
    assert saved["raw_trade_retention_hours"] == 12
    assert orchestrator.database.get_setting("storage_max_bytes") == max_bytes
    assert orchestrator.database.get_setting("raw_trade_retention_hours") == 12
    assert orchestrator._storage_maintenance_requested is True  # noqa: SLF001
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_manual_reset_keeps_event_loop_and_health_responsive_during_writer_contention(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))
    asyncio.run(orchestrator.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000))
    writer_owned = threading.Event()
    release_writer = threading.Event()

    def hold_maintenance_writer() -> None:
        with orchestrator.database._lock:  # noqa: SLF001 - simulate storage maintenance
            writer_owned.set()
            release_writer.wait(timeout=2)

    worker = threading.Thread(target=hold_maintenance_writer)
    worker.start()
    assert writer_owned.wait(timeout=1)

    async def exercise() -> None:
        reset = asyncio.create_task(orchestrator.reset_portfolio())
        await asyncio.sleep(0.05)
        assert not reset.done()
        started = time.monotonic()
        await asyncio.sleep(0.02)
        assert time.monotonic() - started < 0.2
        assert orchestrator.database.health_check() is True
        release_writer.set()
        await asyncio.wait_for(reset, timeout=2)
        await orchestrator.http.close()

    try:
        asyncio.run(exercise())
        assert orchestrator.broker.initialized is False
    finally:
        release_writer.set()
        worker.join(timeout=2)
        orchestrator.database.close()


def test_enrichment_prioritizes_holdings_over_new_candidate_burst(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    held_mint = "held-mint"
    orchestrator.features.tokens[held_mint] = TokenState(
        mint=held_mint,
        last_event_at=now - timedelta(minutes=10),
    )
    orchestrator.broker.positions[held_mint] = Position(
        position_id="held-position",
        mint=held_mint,
        symbol="HELD",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=now - timedelta(minutes=5),
        entry_fill_id="entry-fill",
    )
    for index in range(25):
        mint = f"new-mint-{index}"
        orchestrator.features.tokens[mint] = TokenState(
            mint=mint,
            last_event_at=now + timedelta(seconds=index),
        )

    candidates = orchestrator._enrichment_candidates()  # noqa: SLF001

    assert len(candidates) == 20
    assert candidates[0].mint == held_mint
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def _safe_mint_account() -> dict[str, object]:
    raw = bytearray(82)
    struct.pack_into("<I", raw, 0, 0)
    struct.pack_into("<Q", raw, 36, 1_000_000_000_000_000)
    raw[44] = 6
    raw[45] = 1
    struct.pack_into("<I", raw, 46, 0)
    return {"owner": SPL_TOKEN_PROGRAM, "raw": bytes(raw)}


def test_candidate_accounts_batch_mint_safety_and_exact_pumpswap_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    curve_mint = "CurveMint".ljust(40, "1")
    swap_mint = "SwapMint".ljust(40, "1")
    pool = "Pool".ljust(40, "1")
    base_vault = "BaseVault".ljust(40, "1")
    quote_vault = "QuoteVault".ljust(40, "1")
    quote = "So11111111111111111111111111111111111111112"
    orchestrator.features.tokens[curve_mint] = TokenState(
        mint=curve_mint,
        last_event_at=now,
        last_slot=50,
        sources={"solana:pump"},
    )
    orchestrator.features.tokens[swap_mint] = TokenState(
        mint=swap_mint,
        venue="pump_swap",
        pool_address=pool,
        last_event_at=now,
        last_slot=50,
        sources={"solana:pump_swap"},
    )
    calls: list[tuple[list[str], int | None, bool]] = []

    async def multiple_accounts(
        addresses: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> dict[str, object]:
        calls.append((addresses, min_context_slot, critical))
        return {
            "slot": 51,
            "accounts": {
                curve_mint: _safe_mint_account(),
                swap_mint: _safe_mint_account(),
                pool: {"owner": PUMP_AMM_PROGRAM, "raw": b"pool"},
            },
        }

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", multiple_accounts)
    monkeypatch.setattr(
        orchestrator.solana,
        "decode_pump_swap_pool",
        lambda _raw: {
            "base_mint": swap_mint,
            "quote_mint": quote,
            "pool_base_token_account": base_vault,
            "pool_quote_token_account": quote_vault,
        },
    )

    asyncio.run(orchestrator._verify_candidate_accounts(now, set()))  # noqa: SLF001

    assert len(calls) == 1
    assert set(calls[0][0]) == {curve_mint, swap_mint, pool}
    assert calls[0][1:] == (50, False)
    assert orchestrator.features.tokens[curve_mint].enrichment["mint_safety"]["safe"] is True
    swap = orchestrator.features.tokens[swap_mint]
    assert swap.enrichment["mint_safety"]["safe"] is True
    assert swap.route_verified is True
    assert swap.quote_mint == quote
    assert swap.pool_base_token_account == base_vault
    assert swap.pool_quote_token_account == quote_vault
    assert orchestrator.database.list_decisions(10) == []
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_candidate_batch_isolates_partial_stale_and_mismatched_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    safe_mint = "SafeMint".ljust(40, "1")
    missing_mint = "MissingMint".ljust(40, "1")
    stale_mint = "StaleMint".ljust(40, "1")
    swap_mint = "WrongRouteMint".ljust(40, "1")
    pool = "WrongPool".ljust(40, "1")
    for mint in (safe_mint, missing_mint):
        orchestrator.features.tokens[mint] = TokenState(
            mint=mint,
            last_event_at=now,
            last_slot=100,
            sources={"solana:pump"},
        )
    orchestrator.features.tokens[stale_mint] = TokenState(
        mint=stale_mint,
        last_event_at=now,
        last_slot=200,
        sources={"solana:pump"},
    )
    orchestrator.features.tokens[swap_mint] = TokenState(
        mint=swap_mint,
        venue="pump_swap",
        pool_address=pool,
        last_event_at=now,
        last_slot=100,
        sources={"solana:pump_swap"},
    )

    async def multiple_accounts(
        _addresses: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> dict[str, object]:
        assert min_context_slot == 100
        assert critical is False
        return {
            "slot": 101,
            "accounts": {
                safe_mint: _safe_mint_account(),
                missing_mint: None,
                stale_mint: _safe_mint_account(),
                swap_mint: _safe_mint_account(),
                pool: {"owner": PUMP_AMM_PROGRAM, "raw": b"pool"},
            },
        }

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", multiple_accounts)
    monkeypatch.setattr(
        orchestrator.solana,
        "decode_pump_swap_pool",
        lambda _raw: {
            "base_mint": "DifferentMint".ljust(40, "1"),
            "quote_mint": "So11111111111111111111111111111111111111112",
        },
    )
    asyncio.run(orchestrator._verify_candidate_accounts(now, set()))  # noqa: SLF001

    assert orchestrator.features.tokens[safe_mint].enrichment["mint_safety"]["safe"] is True
    assert "mint_safety" not in orchestrator.features.tokens[missing_mint].enrichment
    assert "mint_safety" not in orchestrator.features.tokens[stale_mint].enrichment
    assert orchestrator.features.tokens[swap_mint].route_verified is False
    assert missing_mint in orchestrator._candidate_verification_retry_at  # noqa: SLF001
    assert stale_mint in orchestrator._candidate_verification_retry_at  # noqa: SLF001
    assert swap_mint in orchestrator._candidate_verification_retry_at  # noqa: SLF001
    assert (
        orchestrator._candidate_verification_targets(  # noqa: SLF001
            now + timedelta(seconds=30), set()
        )
        == []
    )
    retry = orchestrator._candidate_verification_targets(  # noqa: SLF001
        now + timedelta(seconds=61), set()
    )
    assert {target["mint"] for target in retry} == {missing_mint, stale_mint, swap_mint}
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_quota_denial_does_not_mark_candidate_as_attempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "QuotaMint".ljust(40, "1")
    orchestrator.features.tokens[mint] = TokenState(
        mint=mint,
        last_event_at=now,
        last_slot=10,
        sources={"solana:pump"},
    )
    calls = 0

    async def unavailable(
        _addresses: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> None:
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", unavailable)
    asyncio.run(orchestrator._verify_candidate_accounts(now, set()))  # noqa: SLF001
    asyncio.run(
        orchestrator._verify_candidate_accounts(now + timedelta(seconds=15), set())  # noqa: SLF001
    )
    assert calls == 2
    assert mint not in orchestrator._candidate_verification_attempt_at  # noqa: SLF001
    assert mint not in orchestrator._candidate_verification_retry_at  # noqa: SLF001
    assert "mint_safety" not in orchestrator.features.tokens[mint].enrichment
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_candidate_verification_rotates_through_an_aging_burst(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    for index in range(30):
        mint = f"FairMint{index:02d}".ljust(40, "1")
        orchestrator.features.tokens[mint] = TokenState(
            mint=mint,
            last_event_at=now - timedelta(seconds=30 - index),
            last_slot=10 + index,
            sources={"solana:pump"},
        )

    first = orchestrator._candidate_verification_targets(now, set(), limit=10)  # noqa: SLF001
    first_mints = {str(target["mint"]) for target in first}
    assert len(first_mints) == 10
    for mint in first_mints:
        orchestrator._candidate_verification_attempt_at[mint] = now  # noqa: SLF001

    second = orchestrator._candidate_verification_targets(  # noqa: SLF001
        now + timedelta(seconds=1), set(), limit=10
    )
    second_mints = {str(target["mint"]) for target in second}
    assert len(second_mints) == 10
    assert first_mints.isdisjoint(second_mints)
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_candidate_verification_keeps_held_mint_safety_first(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    held = "HeldSafetyMint".ljust(40, "1")
    orchestrator.features.tokens[held] = TokenState(
        mint=held,
        last_event_at=now - timedelta(minutes=5),
        sources={"solana:pump"},
    )
    orchestrator.broker.positions[held] = Position(
        position_id="held-safety-position",
        mint=held,
        symbol="HELD",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=now - timedelta(minutes=5),
        entry_fill_id="held-safety-fill",
    )
    for index in range(50):
        mint = f"BusyMint{index:02d}".ljust(40, "1")
        orchestrator.features.tokens[mint] = TokenState(
            mint=mint,
            last_event_at=now + timedelta(seconds=index),
            sources={"solana:pump"},
        )

    targets = orchestrator._candidate_verification_targets(now, {held}, limit=1)  # noqa: SLF001
    assert len(targets) == 1
    assert targets[0]["mint"] == held
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_candidate_batch_discards_response_after_source_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "SwitchMint".ljust(40, "1")
    orchestrator.features.tokens[mint] = TokenState(
        mint=mint,
        last_event_at=now,
        last_slot=10,
        sources={"solana:pump"},
    )
    requested = asyncio.Event()
    release = asyncio.Event()

    async def delayed(
        _addresses: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> dict[str, object]:
        requested.set()
        await release.wait()
        return {"slot": 11, "accounts": {mint: _safe_mint_account()}}

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", delayed)

    async def exercise() -> None:
        task = asyncio.create_task(orchestrator._verify_candidate_accounts(now, set()))  # noqa: SLF001
        await requested.wait()
        orchestrator.features = type(orchestrator.features)(stale_market_seconds=20)
        release.set()
        await task

    asyncio.run(exercise())
    assert mint not in orchestrator.features.tokens
    assert mint not in orchestrator._candidate_verification_attempt_at  # noqa: SLF001
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_delayed_metadata_cannot_cross_a_source_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "MetadataSwitchMint".ljust(40, "1")
    original = TokenState(mint=mint, last_event_at=now, sources={"solana:pump"})
    orchestrator.features.tokens[mint] = original
    requested = asyncio.Event()
    release = asyncio.Event()

    async def delayed(_mint: str) -> dict[str, str]:
        requested.set()
        await release.wait()
        return {"base_token_name": "Old source metadata"}

    monkeypatch.setattr(orchestrator.http, "dexscreener_token", delayed)

    async def exercise() -> None:
        task = asyncio.create_task(orchestrator._enrich_candidate_metadata(original, now))  # noqa: SLF001
        await requested.wait()
        replacement = type(orchestrator.features)(stale_market_seconds=20)
        replacement.tokens[mint] = TokenState(mint=mint, name="Replacement")
        orchestrator.features = replacement
        release.set()
        await task

    asyncio.run(exercise())
    replacement_state = orchestrator.features.tokens[mint]
    assert replacement_state.name == "Replacement"
    assert replacement_state.enrichment == {}
    assert mint not in orchestrator.enriched_at
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_candidate_batches_never_split_one_token_route_pair() -> None:
    targets = [
        {
            "mint": f"Mint{index}",
            "minimum_slot": index,
            "addresses": [f"Mint{index}", f"Pool{index}"],
        }
        for index in range(60)
    ]
    batches = Orchestrator._candidate_verification_batches(targets)  # noqa: SLF001

    assert [len(addresses) for _targets, addresses, _slot in batches] == [100, 20]
    assert [len(batch_targets) for batch_targets, _addresses, _slot in batches] == [50, 10]
    for batch_targets, addresses, _slot in batches:
        for target in batch_targets:
            assert set(target["addresses"]).issubset(addresses)


def test_exact_checks_run_before_bounded_concurrent_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    for index in range(2):
        mint = f"MetadataMint{index}".ljust(40, "1")
        orchestrator.features.tokens[mint] = TokenState(
            mint=mint,
            last_event_at=now,
            sources={"solana:pump"},
        )
    orchestrator.last_maintenance_at = now
    order: list[str] = []
    active = 0
    maximum_active = 0

    async def verify(_now: datetime, _execution_mints: set[str]) -> None:
        order.append("exact")

    async def metadata(_mint: str) -> None:
        nonlocal active, maximum_active
        order.append("metadata")
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return None

    monkeypatch.setattr(orchestrator, "_verify_candidate_accounts", verify)
    monkeypatch.setattr(orchestrator.http, "dexscreener_token", metadata)
    asyncio.run(orchestrator._enrichment_tick(now))  # noqa: SLF001

    assert order[0] == "exact"
    assert maximum_active == 2
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_candidate_pruning_bounds_causal_caches_and_preserves_ai_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        data_dir=tmp_path, demo_mode=True, candidate_window_minutes=30, _env_file=None
    )
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    stale_at = now - timedelta(minutes=31)
    stale_mint = "StaleMint".ljust(40, "1")
    ai_mint = "AiTrackedMint".ljust(40, "2")
    for mint in (stale_mint, ai_mint):
        orchestrator.features.tokens[mint] = TokenState(mint=mint, last_event_at=stale_at)
        orchestrator._event_order_by_mint[mint] = (10, 10)  # noqa: SLF001
        orchestrator.last_decision_at[mint] = stale_at
        # Only cache membership matters here; the entry is deliberately never evaluated.
        orchestrator.last_recorded_decision[mint] = object()  # type: ignore[assignment]
    # Runtime membership is all pruning needs; no AI assessment is evaluated in this test.
    orchestrator.ai_lab.pending_outcomes[ai_mint] = [object()]  # type: ignore[list-item]
    orchestrator.last_maintenance_at = now

    async def no_exact_checks(_now: datetime, _execution_mints: set[str]) -> None:
        return None

    async def no_metadata(_mint: str) -> None:
        return None

    monkeypatch.setattr(orchestrator, "_verify_candidate_accounts", no_exact_checks)
    monkeypatch.setattr(orchestrator.http, "dexscreener_token", no_metadata)
    asyncio.run(orchestrator._enrichment_tick(now))  # noqa: SLF001

    assert stale_mint not in orchestrator.features.tokens
    assert stale_mint not in orchestrator._event_order_by_mint  # noqa: SLF001
    assert stale_mint not in orchestrator.last_decision_at
    assert stale_mint not in orchestrator.last_recorded_decision
    assert ai_mint in orchestrator.features.tokens
    assert ai_mint in orchestrator._event_order_by_mint  # noqa: SLF001
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_held_pumpswap_route_is_verified_from_program_owned_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    mint = "Mint".ljust(32, "1")
    pool = "Pool".ljust(32, "1")
    quote = "So11111111111111111111111111111111111111112"
    state = TokenState(
        mint=mint,
        venue="pump_swap",
        pool_address=pool,
        route_verified=False,
        last_event_at=datetime.now(UTC),
    )
    orchestrator.features.tokens[mint] = state

    async def account_info(_address: str, *, critical: bool = False) -> dict[str, object]:
        assert critical is True
        return {"owner": PUMP_AMM_PROGRAM, "raw": b"pinned-account"}

    monkeypatch.setattr(orchestrator.http, "solana_account_info", account_info)
    monkeypatch.setattr(
        orchestrator.solana,
        "decode_pump_swap_pool",
        lambda _raw: {"base_mint": mint, "quote_mint": quote},
    )

    assert asyncio.run(orchestrator._verify_pumpswap_route(state, datetime.now(UTC))) is True  # noqa: SLF001
    assert state.route_verified is True
    assert state.quote_mint == quote
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_quiet_held_curve_is_refreshed_without_faking_a_trade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    observed = now - timedelta(minutes=2)
    mint = "Mint".ljust(32, "1")
    curve = "Curve".ljust(32, "1")
    state = TokenState(
        mint=mint,
        symbol="QUIET",
        curve_address=curve,
        last_event_at=observed,
        last_event_id="old-trade",
        last_slot=10,
        virtual_token_reserves=1_000_000_000,
        virtual_quote_reserves=2_000_000_000,
        real_token_reserves=800_000_000,
    )
    orchestrator.features.tokens[mint] = state
    orchestrator.broker.positions[mint] = Position(
        position_id="held-position",
        mint=mint,
        symbol="QUIET",
        token_units=100_000,
        entry_cost_lamports=100_000,
        book_value_lamports=100_000,
        opened_at=observed,
        entry_fill_id="entry-fill",
    )
    monkeypatch.setattr(
        orchestrator.solana,
        "decode_pump_bonding_curve",
        lambda _raw: {
            "virtual_token_reserves": 900_000_000,
            "virtual_quote_reserves": 3_000_000_000,
            "real_token_reserves": 700_000_000,
            "complete": False,
        },
    )

    receipts, refreshed, slot = orchestrator._apply_position_watchdog_result(  # noqa: SLF001
        [
            {
                "mint": mint,
                "venue": "pump_curve",
                "curve_address": curve,
                "pool_address": "",
                "pool_base_token_account": "",
                "pool_quote_token_account": "",
            }
        ],
        {
            "slot": 11,
            "accounts": {
                curve: {"owner": PUMP_PROGRAM, "raw": b"pinned-curve-account"},
            },
        },
        now,
    )

    position = orchestrator.broker.positions[mint]
    assert receipts == []
    assert refreshed == {mint}
    assert slot == 11
    assert state.last_event_at == observed
    assert len(state.trades) == 0
    assert state.last_reserve_at == now
    assert state.last_reserve_event_id == f"solana-rpc:11:{mint}"
    assert state.last_reserve_signature is None
    assert position.mark_is_stale is False
    assert position.mark_is_executable is True
    assert position.last_marked_at == now
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_pumpswap_token_account_decoder_rejects_uninitialized_layout() -> None:
    mint_bytes = bytes(range(32))
    authority_bytes = bytes(range(32, 64))
    raw = bytearray(165)
    raw[:32] = mint_bytes
    raw[32:64] = authority_bytes
    raw[64:72] = (123_456).to_bytes(8, "little")
    raw[108] = 1

    decoded = SolanaLogProvider.decode_token_account(raw)
    assert decoded == {
        "mint": b58encode(mint_bytes),
        "authority": b58encode(authority_bytes),
        "amount": 123_456,
        "state": 1,
    }
    raw[108] = 0
    assert SolanaLogProvider.decode_token_account(raw) is None


def test_position_watchdog_batches_holdings_and_uses_adaptive_provider_pacing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    addresses: list[str] = []
    for index in range(2):
        mint = f"Mint{index}".ljust(32, "1")
        curve = f"Curve{index}".ljust(32, "1")
        orchestrator.features.tokens[mint] = TokenState(
            mint=mint,
            curve_address=curve,
            last_slot=10,
        )
        orchestrator.broker.positions[mint] = Position(
            position_id=f"position-{index}",
            mint=mint,
            symbol=f"P{index}",
            token_units=1,
            entry_cost_lamports=1,
            book_value_lamports=1,
            opened_at=now,
            entry_fill_id=f"fill-{index}",
        )

    async def multiple_accounts(
        requested: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> None:
        addresses.extend(requested)
        assert min_context_slot == 10
        assert critical is False
        return None

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", multiple_accounts)
    assert asyncio.run(orchestrator._position_watchdog_tick(now)) == []  # noqa: SLF001
    assert len(addresses) == 2
    assert len(set(addresses)) == 2
    assert orchestrator._position_watchdog_interval_seconds() == 8.0  # noqa: SLF001

    orchestrator.provider_configuration = ProviderConfiguration(
        solana=ProviderPolicy(
            label="Small free plan",
            requests_per_minute=300,
            monthly_limit=250_000,
        )
    )
    asyncio.run(
        orchestrator.quota.reconfigure(
            orchestrator.provider_configuration.plans(),
            allow_billable=False,
        )
    )
    assert orchestrator._position_watchdog_interval_seconds() > 8.0  # noqa: SLF001

    orchestrator.provider_configuration = ProviderConfiguration(
        solana=ProviderPolicy(
            label="Bounded paid plan",
            requests_per_minute=600,
            monthly_limit=10_000_000,
            paid_mode=True,
        )
    )
    asyncio.run(
        orchestrator.quota.reconfigure(
            orchestrator.provider_configuration.plans(),
            allow_billable=True,
        )
    )
    assert orchestrator._position_watchdog_interval_seconds() == 2.0  # noqa: SLF001
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_position_watchdog_isolates_future_slots_and_chunks_long_lived_holdings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    for index in range(101):
        mint = f"Mint{index:03d}".ljust(32, "1")
        curve = f"Curve{index:03d}".ljust(32, "1")
        orchestrator.features.tokens[mint] = TokenState(
            mint=mint,
            curve_address=curve,
            last_slot=1_000_000 if index == 100 else 10,
        )
        orchestrator.broker.positions[mint] = Position(
            position_id=f"position-{index}",
            mint=mint,
            symbol=f"P{index}",
            token_units=1,
            entry_cost_lamports=1,
            book_value_lamports=1,
            opened_at=now + timedelta(microseconds=index),
            entry_fill_id=f"fill-{index}",
        )

    calls: list[tuple[int, int | None]] = []

    async def multiple_accounts(
        requested: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> None:
        assert critical is False
        calls.append((len(requested), min_context_slot))
        return None

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", multiple_accounts)
    assert asyncio.run(orchestrator._position_watchdog_tick(now)) == []  # noqa: SLF001
    assert calls == [(100, 10), (1, 1_000_000)]
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_position_watchdog_discards_live_response_after_demo_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "Mint".ljust(32, "1")
    curve = "Curve".ljust(32, "1")
    state = TokenState(
        mint=mint,
        curve_address=curve,
        last_slot=10,
        virtual_token_reserves=1_000_000,
        virtual_quote_reserves=2_000_000,
        real_token_reserves=800_000,
    )
    orchestrator.features.tokens[mint] = state
    orchestrator.broker.positions[mint] = Position(
        position_id="position",
        mint=mint,
        symbol="TEST",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=now,
        entry_fill_id="fill",
    )

    async def multiple_accounts(
        _requested: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> dict[str, object]:
        assert min_context_slot == 10
        assert critical is False
        return {
            "slot": 11,
            "accounts": {curve: {"owner": PUMP_PROGRAM, "raw": b"curve"}},
        }

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", multiple_accounts)
    monkeypatch.setattr(
        orchestrator.solana,
        "decode_pump_bonding_curve",
        lambda _raw: {
            "virtual_token_reserves": 900_000,
            "virtual_quote_reserves": 3_000_000,
            "real_token_reserves": 700_000,
        },
    )

    assert asyncio.run(orchestrator._position_watchdog_tick(now)) == []  # noqa: SLF001
    assert state.last_reserve_at is None
    assert state.virtual_quote_reserves == 2_000_000
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_full_queue_backpressures_held_events_instead_of_dropping_them(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    orchestrator.running = True
    orchestrator.event_queue = asyncio.PriorityQueue(maxsize=1)
    now = datetime.now(UTC)
    candidate = "candidate"
    held = "held"
    orchestrator.features.tokens[candidate] = TokenState(mint=candidate, last_event_at=now)
    orchestrator.features.tokens[held] = TokenState(mint=held, last_event_at=now)
    orchestrator.broker.positions[held] = Position(
        position_id="held-position",
        mint=held,
        symbol="HELD",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=now,
        entry_fill_id="entry",
    )
    low = MarketEvent(
        event_id="candidate-trade",
        source="test",
        kind=EventKind.TRADE,
        mint=candidate,
        received_at=now,
        payload={"is_buy": True},
    )
    critical = low.model_copy(update={"event_id": "held-trade", "mint": held})

    async def exercise() -> tuple[int, int, MarketEvent]:
        await orchestrator.enqueue_event(low)
        waiting = asyncio.create_task(orchestrator.enqueue_event(critical))
        await asyncio.sleep(0)
        assert waiting.done() is False
        first = orchestrator.event_queue.get_nowait()
        assert first[2].event_id == low.event_id
        orchestrator.event_queue.task_done()
        await waiting
        return orchestrator.event_queue.get_nowait()

    priority, _sequence, queued = asyncio.run(exercise())
    assert priority == 0
    assert queued.event_id == critical.event_id
    assert orchestrator.events_dropped == 0
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_full_queue_marks_only_the_dropped_candidate_integrity_window(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    orchestrator.running = True
    orchestrator.event_queue = asyncio.PriorityQueue(maxsize=1)
    now = datetime.now(UTC)
    queued_mint = "queued-candidate"
    dropped_mint = "dropped-candidate"
    orchestrator.features.tokens[queued_mint] = TokenState(mint=queued_mint, last_event_at=now)
    orchestrator.features.tokens[dropped_mint] = TokenState(mint=dropped_mint, last_event_at=now)
    queued = MarketEvent(
        event_id="queued-candidate-trade",
        source="test",
        kind=EventKind.TRADE,
        mint=queued_mint,
        received_at=now,
        payload={"is_buy": True},
    )
    dropped = queued.model_copy(
        update={"event_id": "dropped-candidate-trade", "mint": dropped_mint}
    )

    async def exercise() -> None:
        await orchestrator.enqueue_event(queued)
        await orchestrator.enqueue_event(dropped)
        await orchestrator.http.close()

    asyncio.run(exercise())

    assert orchestrator.events_dropped == 1
    assert orchestrator.event_pipeline_status()["shed_candidate_events"] == 1
    assert dropped_mint in orchestrator._integrity_mint_gap_at  # noqa: SLF001
    assert queued_mint not in orchestrator._integrity_mint_gap_at  # noqa: SLF001
    assert orchestrator._integrity_learning_window_complete(dropped_mint, now) is False  # noqa: SLF001
    assert orchestrator._integrity_learning_window_complete(queued_mint, now) is True  # noqa: SLF001
    orchestrator.database.close()


def test_recent_pipeline_windows_are_bounded_and_distinguish_local_shedding(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    orchestrator._record_pipeline_recent(  # noqa: SLF001 - bounded telemetry boundary
        "enqueued", observed_at=now - timedelta(hours=2), count=100
    )
    orchestrator._record_pipeline_recent(  # noqa: SLF001
        "enqueued", observed_at=now - timedelta(minutes=10), count=5
    )
    orchestrator._record_pipeline_recent("enqueued", observed_at=now, count=3)  # noqa: SLF001
    orchestrator._record_pipeline_recent(  # noqa: SLF001
        "processed", observed_at=now, lag_seconds=0.2
    )
    orchestrator._record_pipeline_recent(  # noqa: SLF001
        "processed", observed_at=now, lag_seconds=12.0
    )
    orchestrator._record_pipeline_recent("shed", observed_at=now)  # noqa: SLF001
    orchestrator._record_pipeline_recent("expired", observed_at=now)  # noqa: SLF001

    windows = orchestrator._recent_pipeline_windows(now)  # noqa: SLF001
    assert windows["5m"] == {
        "received": 4,
        "processed": 2,
        "shed": 1,
        "expired": 1,
        "reordered": 0,
        "dropped": 2,
        "drop_fraction": 0.5,
        "processing_lag_p50_seconds": 0.25,
        "processing_lag_p95_seconds": 30.0,
    }
    assert windows["1h"]["received"] == 9
    assert len(orchestrator._pipeline_recent) == 3  # noqa: SLF001
    orchestrator.database.close()


def test_recent_pipeline_windows_are_thread_safe_during_dashboard_reads(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    start = threading.Event()
    errors: list[BaseException] = []

    def write_buckets() -> None:
        start.wait()
        try:
            for index in range(4_000):
                orchestrator._record_pipeline_recent(  # noqa: SLF001
                    "processed",
                    observed_at=now + timedelta(seconds=index),
                    lag_seconds=index % 30,
                )
        except BaseException as exc:  # pragma: no cover - asserted in the caller
            errors.append(exc)

    def read_windows() -> None:
        start.wait()
        try:
            for index in range(500):
                orchestrator._recent_pipeline_windows(  # noqa: SLF001
                    now + timedelta(seconds=index)
                )
        except BaseException as exc:  # pragma: no cover - asserted in the caller
            errors.append(exc)

    writer = threading.Thread(target=write_buckets)
    reader = threading.Thread(target=read_windows)
    writer.start()
    reader.start()
    start.set()
    writer.join(timeout=10)
    reader.join(timeout=10)

    assert not writer.is_alive()
    assert not reader.is_alive()
    assert errors == []
    assert len(orchestrator._pipeline_recent) <= 3_601  # noqa: SLF001
    orchestrator.database.close()


def test_storage_wal_pressure_is_observational_and_thresholded() -> None:
    quiet = Orchestrator._storage_health_view(  # noqa: SLF001
        {"database_bytes": 1_000_000_000, "wal_bytes": 10_000_000}
    )
    watch = Orchestrator._storage_health_view(  # noqa: SLF001
        {"database_bytes": 1_000_000_000, "wal_bytes": 120_000_000}
    )
    attention = Orchestrator._storage_health_view(  # noqa: SLF001
        {"database_bytes": 1_000_000_000, "wal_bytes": 600_000_000}
    )
    assert quiet["wal_pressure_state"] == "quiet"
    assert watch["wal_pressure_state"] == "watch"
    assert attention["wal_pressure_state"] == "attention"
    assert attention["wal_database_fraction"] == 0.6


def test_worker_fast_forwards_expired_candidate_ticks_but_not_protected_events(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path,
        demo_mode=True,
        stale_market_seconds=5,
        event_batch_wait_ms=1,
        _env_file=None,
    )
    orchestrator = Orchestrator(settings)
    orchestrator.running = True
    now = datetime.now(UTC)
    mint = "expired-candidate"
    orchestrator.features.tokens[mint] = TokenState(mint=mint, last_event_at=now)
    expired = MarketEvent(
        event_id="expired-candidate-trade",
        source="test",
        kind=EventKind.TRADE,
        mint=mint,
        received_at=now - timedelta(seconds=30),
        payload={"is_buy": True},
    )

    async def exercise() -> None:
        await orchestrator.enqueue_event(expired)
        worker = asyncio.create_task(orchestrator._event_worker_loop())  # noqa: SLF001
        await asyncio.wait_for(orchestrator.event_queue.join(), timeout=2)
        orchestrator.stop_event.set()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await orchestrator.http.close()

    asyncio.run(exercise())

    assert orchestrator.events_processed == 0
    assert orchestrator.expired_candidate_events == 1
    assert orchestrator.events_dropped == 1
    assert orchestrator.event_pipeline_status()["shed_candidate_events"] == 0
    assert mint in orchestrator._integrity_mint_gap_at  # noqa: SLF001
    assert orchestrator._expired_candidate_event(0, expired, now) is False  # noqa: SLF001
    orchestrator.database.close()


def test_candidate_scoring_cooldown_adapts_only_when_queue_pressure_is_extreme(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path,
        demo_mode=True,
        decision_cooldown_seconds=5,
        _env_file=None,
    )
    orchestrator = Orchestrator(settings)
    orchestrator.event_queue = asyncio.PriorityQueue(maxsize=10)
    now = datetime.now(UTC)
    event = MarketEvent(
        event_id="pressure",
        source="test",
        kind=EventKind.TRADE,
        mint="candidate",
        received_at=now,
        payload={"is_buy": True},
    )

    assert orchestrator._candidate_decision_cooldown_seconds() == 5  # noqa: SLF001
    for sequence in range(9):
        orchestrator.event_queue.put_nowait((2, sequence, event))
    assert orchestrator._candidate_decision_cooldown_seconds() == 30  # noqa: SLF001

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_event_batch_wait_is_skipped_when_a_backlog_already_exists(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        demo_mode=True,
        event_batch_wait_ms=25,
        _env_file=None,
    )
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    event = MarketEvent(
        event_id="already-queued",
        source="test",
        kind=EventKind.TRADE,
        mint="queued-mint",
        received_at=now,
        payload={"is_buy": True},
    )

    assert orchestrator._event_batch_wait_seconds() == 0.025  # noqa: SLF001
    orchestrator.event_queue.put_nowait((2, 1, event))
    assert orchestrator._event_batch_wait_seconds() == 0.0  # noqa: SLF001
    queued = orchestrator.event_queue.get_nowait()
    assert queued[2] == event
    orchestrator.event_queue.task_done()

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_integrity_learning_waits_for_full_clean_window_after_candidate_shedding(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    affected = "affected-mint"
    unrelated = "unrelated-mint"

    assert orchestrator._integrity_learning_window_complete(affected, now) is True  # noqa: SLF001
    orchestrator._note_integrity_mint_gap(affected, now)  # noqa: SLF001
    assert orchestrator._integrity_learning_window_complete(affected, now) is False  # noqa: SLF001
    assert orchestrator._integrity_learning_window_complete(unrelated, now) is True  # noqa: SLF001
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(affected, now + timedelta(seconds=299))
        is False
    )
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(affected, now + timedelta(seconds=300))
        is True
    )
    assert affected not in orchestrator._integrity_mint_gap_at  # noqa: SLF001

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_integrity_learning_waits_after_source_start_and_provider_reconnect(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "continuity-mint"
    orchestrator.solana.connected = True
    orchestrator._mark_integrity_stream_gap(now)  # noqa: SLF001

    assert orchestrator._integrity_learning_window_complete(mint, now) is False  # noqa: SLF001
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(mint, now + timedelta(seconds=300)) is True
    )

    # A reconnect counter may rise at the start of a long outage. Disconnected time must not
    # satisfy the clean-window requirement before the provider actually recovers.
    orchestrator.solana.connected = False
    orchestrator.solana.reconnects += 1
    disconnected_at = now + timedelta(seconds=301)
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(mint, disconnected_at) is False
    )
    recovered_at = disconnected_at + timedelta(seconds=600)
    orchestrator.solana.connected = True
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(mint, recovered_at) is False
    )
    assert orchestrator._integrity_stream_gap_at == recovered_at  # noqa: SLF001
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(
            mint, recovered_at + timedelta(seconds=299)
        )
        is False
    )
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(
            mint, recovered_at + timedelta(seconds=300)
        )
        is True
    )

    orchestrator.solana.connected = False
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(
            mint, recovered_at + timedelta(seconds=600)
        )
        is False
    )

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_stream_incident_observer_starts_integrity_window_at_confirmed_recovery(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    disconnected_at = datetime(2026, 1, 1, tzinfo=UTC)
    recovered_at = disconnected_at + timedelta(minutes=10)

    async def exercise() -> None:
        await orchestrator._update_stream_incident(  # noqa: SLF001
            disconnected_at,
            {"reconnects": 1, "connected": False, "last_error": "temporary"},
        )
        assert orchestrator._integrity_stream_was_healthy is False  # noqa: SLF001
        await orchestrator._update_stream_incident(  # noqa: SLF001
            recovered_at,
            {"reconnects": 1, "connected": True, "last_error": None},
        )
        assert orchestrator._integrity_stream_was_healthy is True  # noqa: SLF001
        assert orchestrator._integrity_stream_gap_at == recovered_at  # noqa: SLF001
        await orchestrator.http.close()

    asyncio.run(exercise())
    orchestrator.database.close()


def test_failed_worker_batch_marks_each_represented_mint_without_global_pause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        data_dir=tmp_path,
        demo_mode=True,
        event_batch_size=10,
        event_batch_wait_ms=1,
        _env_file=None,
    )
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    first_mint = "first-failed-mint"
    second_mint = "second-failed-mint"
    first = MarketEvent(
        event_id="first-failed-event",
        source="test",
        kind=EventKind.TRADE,
        mint=first_mint,
        received_at=now,
        payload={"is_buy": True},
    )
    second = first.model_copy(update={"event_id": "second-failed-event", "mint": second_mint})
    handled = 0

    async def fail_partway_through_batch(
        _event: MarketEvent,
        *,
        sequence: int | None = None,
    ) -> bool:
        nonlocal handled
        assert sequence is not None
        handled += 1
        if handled == 2:
            raise RuntimeError("test batch failure")
        return True

    monkeypatch.setattr(orchestrator, "_handle_persisted_event", fail_partway_through_batch)

    async def exercise() -> None:
        orchestrator.event_queue.put_nowait((2, 1, first))
        orchestrator.event_queue.put_nowait((2, 2, second))
        worker = asyncio.create_task(orchestrator._event_worker_loop())  # noqa: SLF001
        await asyncio.wait_for(orchestrator.event_queue.join(), timeout=2)
        orchestrator.stop_event.set()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await orchestrator.http.close()

    asyncio.run(exercise())

    assert handled == 2
    assert first_mint in orchestrator._integrity_mint_gap_at  # noqa: SLF001
    assert second_mint in orchestrator._integrity_mint_gap_at  # noqa: SLF001
    assert orchestrator._integrity_stream_gap_at is None  # noqa: SLF001
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete("unrelated", now) is True
    )
    incidents = orchestrator.database.list_incidents(10)
    assert any(incident.scope == "market_event_worker" for incident in incidents)
    orchestrator.database.close()


def test_failed_worker_batch_with_unknown_mint_fails_closed_source_wide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        data_dir=tmp_path,
        demo_mode=True,
        event_batch_wait_ms=1,
        _env_file=None,
    )
    orchestrator = Orchestrator(settings)
    event = MarketEvent(
        event_id="unknown-failed-event",
        source="test",
        kind=EventKind.CREATE,
        mint=None,
        received_at=datetime.now(UTC),
        payload={},
    )

    async def fail_event(
        _event: MarketEvent,
        *,
        sequence: int | None = None,
    ) -> None:
        assert sequence is not None
        raise RuntimeError("test unidentified failure")

    monkeypatch.setattr(orchestrator, "_handle_persisted_event", fail_event)

    async def exercise() -> None:
        orchestrator.event_queue.put_nowait((1, 1, event))
        worker = asyncio.create_task(orchestrator._event_worker_loop())  # noqa: SLF001
        await asyncio.wait_for(orchestrator.event_queue.join(), timeout=2)
        orchestrator.stop_event.set()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await orchestrator.http.close()

    asyncio.run(exercise())

    assert orchestrator._integrity_stream_gap_at is not None  # noqa: SLF001
    assert orchestrator._integrity_mint_gap_at == {}  # noqa: SLF001
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete(
            "unrelated", orchestrator._integrity_stream_gap_at
        )
        is False
    )
    orchestrator.database.close()


def test_source_restart_begins_a_new_integrity_continuity_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)

    async def idle_source(_handler: object, stop: asyncio.Event) -> None:
        await stop.wait()

    monkeypatch.setattr(orchestrator.solana, "run", idle_source)

    async def exercise() -> None:
        before = datetime.now(UTC)
        await orchestrator._start_source()  # noqa: SLF001
        assert orchestrator._integrity_stream_gap_at is not None  # noqa: SLF001
        assert orchestrator._integrity_stream_gap_at >= before  # noqa: SLF001
        orchestrator.source_stop.set()
        assert orchestrator.source_task is not None
        await orchestrator.source_task
        await orchestrator.http.close()

    asyncio.run(exercise())
    orchestrator.database.close()


def test_integrity_gap_tracking_fails_closed_at_bounded_cardinality(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    orchestrator._max_integrity_gap_mints = 1  # noqa: SLF001
    now = datetime.now(UTC)

    orchestrator._note_integrity_mint_gap("first", now)  # noqa: SLF001
    orchestrator._note_integrity_mint_gap("second", now + timedelta(seconds=1))  # noqa: SLF001

    assert orchestrator._integrity_mint_gap_at == {}  # noqa: SLF001
    assert orchestrator._integrity_stream_gap_at == now + timedelta(seconds=1)  # noqa: SLF001
    assert (  # noqa: SLF001
        orchestrator._integrity_learning_window_complete("unrelated", now + timedelta(seconds=2))
        is False
    )

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_priority_inversion_cannot_reverse_one_mints_market_chronology(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "priority-ordered-mint"
    newer = MarketEvent(
        event_id="newer-critical",
        source="demo:test",
        kind=EventKind.TRADE,
        mint=mint,
        slot=55,
        received_at=now + timedelta(seconds=10),
        payload={"is_buy": True, "token_amount": 10, "quote_amount": 10},
    )
    older = MarketEvent(
        event_id="older-candidate",
        source="demo:test",
        kind=EventKind.TRADE,
        mint=mint,
        slot=55,
        received_at=now + timedelta(seconds=2),
        payload={"is_buy": False, "token_amount": 20, "quote_amount": 20},
    )

    async def exercise() -> None:
        assert await orchestrator._handle_persisted_event(newer, sequence=20) is True  # noqa: SLF001
        assert await orchestrator._handle_persisted_event(older, sequence=10) is False  # noqa: SLF001
        await orchestrator.http.close()

    asyncio.run(exercise())
    state = orchestrator.features.tokens[mint]
    assert state.last_event_id == newer.event_id
    assert state.last_event_at == newer.received_at
    assert len(state.trades) == 1
    assert orchestrator.reordered_events == 1
    assert mint in orchestrator._integrity_mint_gap_at  # noqa: SLF001
    orchestrator.database.close()


def test_restart_rebuild_uses_solana_slots_instead_of_arrival_time(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    database = Database(settings.database_path)
    now = datetime.now(UTC)
    mint = "restart-causal-mint"
    curve = "Curve".ljust(32, "1")
    newer_state = MarketEvent(
        event_id="slot-20-arrived-first",
        source=f"solana:{PUMP_PROGRAM}",
        kind=EventKind.TRADE,
        mint=mint,
        slot=20,
        received_at=now,
        payload={
            "bonding_curve": curve,
            "is_buy": True,
            "user": "newer-wallet",
            "token_amount": 10,
            "sol_amount": 10,
            "virtual_token_reserves": 900,
            "virtual_sol_reserves": 4_000,
            "real_token_reserves": 700,
        },
    )
    delayed_older_state = MarketEvent(
        event_id="slot-10-arrived-later",
        source=f"solana:{PUMP_PROGRAM}",
        kind=EventKind.TRADE,
        mint=mint,
        slot=10,
        received_at=now + timedelta(seconds=1),
        payload={
            "bonding_curve": curve,
            "is_buy": False,
            "user": "older-wallet",
            "token_amount": 20,
            "sol_amount": 20,
            "virtual_token_reserves": 1_000,
            "virtual_sol_reserves": 2_000,
            "real_token_reserves": 800,
        },
    )
    assert database.append_events([newer_state, delayed_older_state]) == {
        newer_state.event_id,
        delayed_older_state.event_id,
    }
    database.close()

    orchestrator = Orchestrator(settings)
    rebuilt = orchestrator.features.tokens[mint]
    assert rebuilt.last_slot == 20
    assert rebuilt.last_reserve_slot == 20
    assert rebuilt.last_event_id == newer_state.event_id
    assert rebuilt.virtual_quote_reserves == 4_000
    assert [trade.user for trade in rebuilt.trades] == ["older-wallet", "newer-wallet"]
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_watchdog_snapshot_fences_only_preexisting_same_or_lower_slot_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=False, _env_file=None)
    orchestrator = Orchestrator(settings)
    requested_at = datetime.now(UTC) - timedelta(seconds=5)
    mint = "Mint".ljust(32, "1")
    curve = "Curve".ljust(32, "1")
    state = TokenState(
        mint=mint,
        symbol="WATCH",
        curve_address=curve,
        last_event_at=requested_at,
        last_event_id="stream-slot-10",
        last_slot=10,
        last_reserve_at=requested_at,
        last_reserve_slot=10,
        last_reserve_event_id="stream-slot-10",
        last_reserve_signature="stream-signature",
        virtual_token_reserves=1_000_000,
        virtual_quote_reserves=2_000_000,
        real_token_reserves=800_000,
    )
    orchestrator.features.tokens[mint] = state
    orchestrator.broker.positions[mint] = Position(
        position_id="position",
        mint=mint,
        symbol="WATCH",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=requested_at,
        entry_fill_id="fill",
    )
    invalid_mint = "Invalid".ljust(32, "1")
    invalid_curve = "InvalidCurve".ljust(32, "1")
    invalid_state = TokenState(
        mint=invalid_mint,
        symbol="INVALID",
        curve_address=invalid_curve,
        last_event_at=requested_at,
        last_slot=10,
        last_reserve_at=requested_at,
        last_reserve_slot=10,
        virtual_token_reserves=1_000_000,
        virtual_quote_reserves=2_000_000,
        real_token_reserves=800_000,
    )
    orchestrator.features.tokens[invalid_mint] = invalid_state
    orchestrator.broker.positions[invalid_mint] = Position(
        position_id="invalid-position",
        mint=invalid_mint,
        symbol="INVALID",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=requested_at,
        entry_fill_id="invalid-fill",
    )
    orchestrator._event_sequence = 7  # noqa: SLF001

    async def multiple_accounts(
        _requested: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> dict[str, object]:
        assert min_context_slot == 10
        assert critical is False
        return {
            "slot": 11,
            "accounts": {
                curve: {"owner": PUMP_PROGRAM, "raw": b"curve"},
                invalid_curve: {"owner": "wrong-owner", "raw": b"curve"},
            },
        }

    monkeypatch.setattr(orchestrator.http, "solana_multiple_accounts", multiple_accounts)
    monkeypatch.setattr(
        orchestrator.solana,
        "decode_pump_bonding_curve",
        lambda _raw: {
            "virtual_token_reserves": 900_000,
            "virtual_quote_reserves": 3_000_000,
            "real_token_reserves": 700_000,
        },
    )
    before_refresh = datetime.now(UTC)
    assert asyncio.run(orchestrator._position_watchdog_tick(requested_at)) == []  # noqa: SLF001
    assert state.last_reserve_at is not None and state.last_reserve_at >= before_refresh
    assert state.last_reserve_event_id == f"solana-rpc:11:{mint}"
    assert state.last_reserve_signature is None
    assert orchestrator._event_order_by_mint[mint] == (11, 7)  # noqa: SLF001
    assert invalid_state.last_reserve_slot == 10
    assert invalid_mint not in orchestrator._event_order_by_mint  # noqa: SLF001

    queued_same_slot = MarketEvent(
        event_id="queued-same-slot",
        source=f"solana:{PUMP_PROGRAM}",
        kind=EventKind.TRADE,
        mint=mint,
        slot=11,
        received_at=state.last_reserve_at - timedelta(milliseconds=1),
    )
    assert orchestrator._accept_event_order(queued_same_slot, 7) is False  # noqa: SLF001
    later_same_slot = queued_same_slot.model_copy(
        update={
            "event_id": "later-same-slot",
            "received_at": state.last_reserve_at + timedelta(milliseconds=1),
        }
    )
    assert orchestrator._accept_event_order(later_same_slot, 8) is True  # noqa: SLF001
    lower_slot = queued_same_slot.model_copy(
        update={"event_id": "lower-slot", "slot": 10, "received_at": state.last_reserve_at}
    )
    assert orchestrator._accept_event_order(lower_slot, 9) is False  # noqa: SLF001
    higher_slot_after_clock_rollback = queued_same_slot.model_copy(
        update={
            "event_id": "higher-slot",
            "slot": 12,
            "received_at": state.last_reserve_at - timedelta(seconds=1),
        }
    )
    assert (  # noqa: SLF001
        orchestrator._accept_event_order(higher_slot_after_clock_rollback, 10) is True
    )
    assert orchestrator.reordered_events == 2
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_heartbeat_uses_latest_reserve_clock_and_provenance_for_each_mint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    requested_at = datetime.now(UTC)
    reserve_at = requested_at + timedelta(seconds=2)
    mint = "heartbeat-causal-mint"
    state = TokenState(
        mint=mint,
        symbol="HEART",
        last_event_at=requested_at,
        last_event_id="older-stream-event",
        last_reserve_at=reserve_at,
        last_reserve_slot=22,
        last_reserve_event_id=f"solana-rpc:22:{mint}",
        reserve_source="solana_rpc:position_watchdog",
        virtual_token_reserves=1_000_000,
        virtual_quote_reserves=2_000_000,
        real_token_reserves=800_000,
    )
    orchestrator.features.tokens[mint] = state
    orchestrator.broker.pending["pending"] = PaperOrder(
        order_id="pending",
        mint=mint,
        symbol="HEART",
        side="buy",
        requested_sol_lamports=1,
        created_at=requested_at,
        fill_after=requested_at,
    )
    orchestrator.running = True
    observed: list[tuple[datetime, str]] = []

    def process_due_orders(**kwargs: object) -> list[object]:
        observed_at = kwargs["now"]
        source_event_id = kwargs["source_event_id"]
        assert isinstance(observed_at, datetime)
        assert isinstance(source_event_id, str)
        observed.append((observed_at, source_event_id))
        return []

    monkeypatch.setattr(orchestrator.broker, "process_due_orders", process_due_orders)
    orchestrator._heartbeat_tick(requested_at)  # noqa: SLF001

    assert observed == [(reserve_at, f"solana-rpc:22:{mint}")]
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_paused_engine_sheds_untracked_candidate_trades(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    mint = "paused-candidate"
    orchestrator.features.tokens[mint] = TokenState(mint=mint, last_event_at=datetime.now(UTC))
    trade = MarketEvent(
        event_id="paused-trade",
        source="test",
        kind=EventKind.TRADE,
        mint=mint,
        received_at=datetime.now(UTC),
        payload={"is_buy": True},
    )

    assert orchestrator.running is False
    assert orchestrator._ignore_untracked_trade(trade) is True  # noqa: SLF001

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_candidate_trade_inside_decision_cooldown_skips_feature_scan(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "cooling-candidate"
    orchestrator.running = True
    orchestrator.features.tokens[mint] = TokenState(mint=mint, last_event_at=now)
    orchestrator.last_decision_at[mint] = now

    def unexpected_snapshot(_mint: str, _now: datetime | None = None) -> None:
        raise AssertionError("cooling candidates must not rebuild a rolling feature snapshot")

    orchestrator.features.snapshot = unexpected_snapshot  # type: ignore[method-assign]
    asyncio.run(
        orchestrator._handle_persisted_event(  # noqa: SLF001
            MarketEvent(
                event_id="cooldown-trade",
                source="test",
                kind=EventKind.TRADE,
                mint=mint,
                received_at=now + timedelta(seconds=1),
                payload={"is_buy": True},
            )
        )
    )

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_program_data_is_accepted_only_inside_the_official_program_log_stack() -> None:
    resources = Path(__file__).parents[1] / "backend" / "signal_arcade" / "resources" / "idl"
    provider = SolanaLogProvider("wss://rpc.example", resources)
    mint = "Mint".ljust(32, "1")

    class FakeDecoder:
        def decode_log_line(
            self, line: str, expected_program: str | None = None
        ) -> tuple[str, str, dict[str, object]] | None:
            if line == "Program data: fixture":
                return (
                    expected_program or PUMP_PROGRAM,
                    "TradeEvent",
                    {
                        "mint": mint,
                        "is_buy": True,
                    },
                )
            return None

    provider.decoder = FakeDecoder()  # type: ignore[assignment]
    attacker = "Attack".ljust(32, "1")
    events = provider.events_from_logs(
        "signature",
        123,
        [
            f"Program {attacker} invoke [1]",
            "Program data: fixture",
            f"Program {attacker} success",
            f"Program {PUMP_PROGRAM} invoke [1]",
            "Program data: fixture",
            f"Program {PUMP_PROGRAM} success",
        ],
    )
    assert len(events) == 1
    assert events[0].source == f"solana:{PUMP_PROGRAM}"
    assert events[0].mint == mint


def test_concurrent_leaderboard_views_share_one_immutable_history_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    calls: list[list[Position] | None] = []

    def counted_leaderboard(
        sort: str = "profit",
        limit: int = 100,
        *,
        positions: list[Position] | None = None,
        quote_currency: str | None = None,
        quote_decimals: int | None = None,
    ) -> dict[str, object]:
        calls.append(positions)
        assert quote_currency == "SOL"
        assert quote_decimals == 9
        time.sleep(0.05)
        return {
            "sort": sort,
            "available_rows": limit,
            "summary": {"closed_trades": 0},
            "rows": [{"rank": rank} for rank in range(limit)],
        }

    monkeypatch.setattr(orchestrator, "leaderboard", counted_leaderboard)

    async def exercise() -> list[dict[str, object]]:
        return await asyncio.gather(
            *(orchestrator.leaderboard_view(sort="profit", limit=2) for _ in range(12))
        )

    results = asyncio.run(exercise())

    assert len(calls) == 1
    assert calls[0] == []
    assert all(len(result["rows"]) == 2 for result in results)  # type: ignore[arg-type]
    assert all(result["available_rows"] == 500 for result in results)
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()
