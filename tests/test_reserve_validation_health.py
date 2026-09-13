"""Reporting cannot turn unknown protocol layouts into price or learning evidence."""

import asyncio
import base64
import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from signal_arcade.api import create_app
from signal_arcade.diagnostics_store import DiagnosticsStore, read_events
from signal_arcade.intelligence import reserve_health
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.intelligence.reserve_health import ReserveValidationHealth
from signal_arcade.intelligence.reserve_refresh import (
    ReserveRefreshRejected,
    reserve_addresses,
    validated_learning_state,
)
from signal_arcade.models import LearningMode, RiskMode
from signal_arcade.orchestrator import Orchestrator
from test_broker import make_decision, make_features
from test_broker_work_budget import held  # noqa: F401
from test_learning import make_decision as learning_decision
from test_learning import make_state
from test_public_reserve_accounts import CAPTURE
from test_v1104_refresh import route_fixture


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(tick=0.0, wall=1_789_028_000.0)
    monkeypatch.setattr(
        reserve_health,
        "time",
        SimpleNamespace(monotonic=lambda: clock.tick, time=lambda: clock.wall),
    )
    return clock


def failure():
    return ReserveRefreshRejected("unreviewed_account_extension", account_type="FeeConfig")


def status(tracker):
    return tracker.status(learning=True, watchdog=True)


def test_request_threshold_time_and_other_sources_do_not_hide_failure(clock):
    tracker = ReserveValidationHealth()
    for tick in (0, 15, 30):
        clock.tick = tick
        clock.wall -= 3600  # Wall-clock changes must not control detection.
        with tracker.batch("learning") as batch:
            for _ in range(20):
                batch.rejected("pump_curve", failure())
            batch.accepted("pump_curve")  # A mixed response cannot erase its failure.
            batch.accepted("pump_swap")
        assert status(tracker)["attention"] is (tick == 30)
    components = status(tracker)["components"]
    assert components[0]["failed_batches"] == 3
    assert components[1]["state"] == "verified"
    assert reserve_health.compact_validation_health(status(tracker)) == [117, 80, 64, 64]
    with tracker.batch("watchdog") as batch:
        batch.accepted("pump_curve")
    assert status(tracker)["attention"]
    inactive = tracker.status(learning=False, watchdog=True)
    assert not inactive["attention"]
    assert inactive["components"][0]["state"] == "blocked"  # Disabled is not recovered.
    assert status(tracker)["attention"]  # Re-enabling cannot hide the saved fault.
    with tracker.batch("learning") as batch:
        batch.accepted("pump_curve")
    assert not status(tracker)["attention"]
    assert status(tracker)["components"][0]["failed_batches"] == 0


def test_fast_burst_no_work_and_ordinary_bad_markets_do_not_alarm(clock):
    tracker = ReserveValidationHealth()
    for _ in range(100):
        with tracker.batch("learning") as batch:
            batch.rejected("pump_curve", failure())
    assert not status(tracker)["attention"]  # Must span at least 30 seconds.
    clock.tick = 600
    with tracker.batch("learning"):
        pass  # A timer alone is not another failed request.
    assert not status(tracker)["attention"]
    other = ReserveValidationHealth()
    for tick in (0, 30, 60):
        clock.tick = tick
        with other.batch("learning") as batch:
            for reason, account in (
                ("stale_slot_or_timestamp", None),
                ("unreviewed_account_extension", "Pool"),
                ("unreviewed_account_extension", "BondingCurve"),
                ("empty_reserves", None),
                ("mint_not_verified_safe", None),
            ):
                batch.rejected("pump_curve", ReserveRefreshRejected(reason, account_type=account))
            batch.accepted("unknown_venue")
    assert not status(other)["attention"]
    assert all(row["state"] == "not_observed" for row in status(other)["components"])
    assert len(other._health) == 4
    assert not status(ReserveValidationHealth())["attention"]  # Restart starts unobserved.


@pytest.mark.parametrize("error", [ValueError, asyncio.CancelledError])
def test_batch_reports_only_completed_validation_and_preserves_exception(clock, error):
    tracker = ReserveValidationHealth()
    for tick in (0, 15, 30):
        clock.tick = tick
        with pytest.raises(error), tracker.batch("learning") as batch:
            batch.rejected("pump_curve", failure())
            raise error()
    assert status(tracker)["attention"]
    with pytest.raises(error), tracker.batch("learning"):
        raise error()  # No result is not recovery.
    assert status(tracker)["attention"]


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
def test_learning_reports_real_rejection_and_recovers_without_fabricated_updates(
    settings, clock, venue
):
    settings.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    engine = Orchestrator(settings)
    engine.learning.mode = LearningMode.SHADOW
    state, valid, _, now = route_fixture(venue)
    engine.features.tokens[state.mint] = state
    before = copy.deepcopy(state)
    invalid = copy.deepcopy(valid)
    account = next(
        a for a in CAPTURE["accounts"] if a["venue"] == venue and a["name"] == "FeeConfig"
    )
    invalid["accounts"][reserve_addresses(state)[1]]["raw"] = (
        base64.b64decode(account["data_base64"]) + b"\x01"
    )  # A future unknown extension beyond the now-reviewed account fields.
    try:
        for tick in (0, 15, 30):
            clock.tick = tick
            engine._apply_learning_reserve_result(
                {state.mint: copy.copy(state)}, {state.mint: state}, invalid, now
            )
        pipeline = engine.event_pipeline_status()
        assert pipeline["reserve_validation"]["attention"]
        assert not pipeline["degraded"]  # This is not market lag or process liveness.
        assert not engine._learning_invalid_routes  # Shared failures cannot ban mints.
        assert engine._learning_refresh_status["checkpoint_updates"] == 0
        assert engine._learning_refresh_status["accepted_routes"] == 0
        assert state == before
        engine._apply_learning_reserve_result(
            {state.mint: copy.copy(state)}, {state.mint: state}, valid, now
        )
        assert not engine.event_pipeline_status()["reserve_validation"]["attention"]
        assert engine._learning_refresh_status["accepted_routes"] == 1
        assert engine._learning_refresh_status["checkpoint_updates"] == 0  # No pending work.
        assert state == before  # Learning-only snapshots still cannot enter the broker.
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("item", CAPTURE["accounts"], ids=lambda row: row["venue"] + row["name"])
def test_watchdog_reports_shared_fault_without_claiming_an_empty_route(held, clock, item):  # noqa: F811
    broker, _, _, _ = held
    state, response, decoder, now = route_fixture(item["venue"])
    verified = validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    engine = Orchestrator(broker.settings)
    engine.broker = broker
    engine.demo_mode = False
    engine.risk_mode = RiskMode.BALANCED
    engine.features.tokens[state.mint] = state
    assert broker.submit_decision(make_decision(now, state.mint))
    assert broker.process_due_orders(
        state=verified,
        features=make_features(now, state.mint),
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    targets = [t for t in engine._position_watchdog_targets()[0] if t["mint"] == state.mint]
    assert targets
    before = copy.deepcopy(state)
    invalid = copy.deepcopy(response)
    invalid["accounts"][item["address"]]["raw"] = base64.b64decode(item["data_base64"]) + b"\x01"
    try:
        for tick in (0, 15, 30):
            clock.tick = tick
            receipts, refreshed, _ = engine._apply_position_watchdog_result(targets, invalid, now)
            assert not receipts and not refreshed
        assert engine._reserve_validation_status()["attention"]
        assert state == before
        assert state.mint in broker.positions
        assert not engine._position_route_probes[state.mint]["verified"]
        assert not engine._learning_invalid_routes
        _, refreshed, _ = engine._apply_position_watchdog_result(targets, response, now)
        assert refreshed == {state.mint}
        assert not engine._reserve_validation_status()["attention"]
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_health_exposes_component_fault_without_failing_liveness(settings, clock, monkeypatch):
    app = create_app(settings)
    engine = app.state.orchestrator
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    engine.learning.mode = LearningMode.SHADOW
    engine.service_running = True
    monkeypatch.setattr(engine, "background_task_status", lambda: {"market": True})
    client = TestClient(app)  # No lifespan: no providers or background tasks are started.
    try:
        for tick in (0, 15, 30):
            clock.tick = tick
            with engine._reserve_validation.batch("learning") as batch:
                batch.rejected("pump_curve", failure())
        health = client.get("/api/v1/health").json()
        assert health["ok"] and not health["degraded"]
        assert health["reserve_validation"]["attention"]
        assert health["reserve_validation"] == health["event_pipeline"]["reserve_validation"]
        engine.learning.mode = LearningMode.OFF
        assert not client.get("/api/v1/health").json()["reserve_validation"]["attention"]
    finally:
        client.close()
        asyncio.run(engine.http.close())
        engine.database.close()


def test_watchdog_fault_exports_without_learning_counters_and_keeps_proof_priority(settings, clock):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    try:
        for tick in (0, 15, 30):
            clock.tick = tick
            with engine._reserve_validation.batch("watchdog") as batch:
                batch.rejected("pump_swap", failure())
        assert not engine.learning.collection_diagnostics.events()
        for i in range(7):
            engine.diagnostics.event({"kind": "proof", "test_sequence": i})
        engine._record_collection_diagnostics()
        assert len(engine.diagnostics.events) == 7  # No proof eviction.
        engine.diagnostics.events.clear()
        engine._record_collection_diagnostics()
        assert len(engine.diagnostics.events) == 1
        event = engine.diagnostics.events[0]
        assert event["kind"] == "reserve_validation"
        expected = [0, 0, 0, 53]  # Inactive, blocked, FeeConfig, unreviewed extension.
        assert event["reserve_validation"] == expected
        engine._collect_diagnostics()
        with_store = DiagnosticsStore(engine.diagnostics.directory)
        try:
            record = json.loads(engine.diagnostics.queue[-1])
            assert with_store.append(record)
            rows = read_events(engine.diagnostics.directory, before=2e9)
            assert rows[0]["record"]["reserve_validation"] == expected
        finally:
            with_store.close()
        engine._record_collection_diagnostics()
        assert not engine.diagnostics.events  # Five-minute cadence still applies.
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("cache_age_seconds", [2, 30])
def test_cached_dashboard_overlays_current_fault_without_mutating_cache(
    settings, clock, cache_age_seconds
):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    engine.learning.mode = LearningMode.SHADOW
    now = datetime.now(UTC)
    saved = {"event_pipeline": {"reserve_validation": engine._reserve_validation_status()}}
    original = copy.deepcopy(saved)
    cached = (time.monotonic(), now - timedelta(seconds=cache_age_seconds), saved)
    try:
        for tick in (0, 15, 30):
            clock.tick = tick
            with engine._reserve_validation.batch("learning") as batch:
                batch.rejected("pump_curve", failure())
        response = engine._snapshot_cache_response(cached)
        assert response["snapshot_age_seconds"] >= cache_age_seconds
        assert response["event_pipeline"]["reserve_validation"]["attention"]
        assert saved == original
        engine.learning.mode = LearningMode.OFF
        inactive = engine._snapshot_cache_response(cached)
        assert not inactive["event_pipeline"]["reserve_validation"]["attention"]
        assert (
            inactive["event_pipeline"]["reserve_validation"]["components"][0]["state"] == "blocked"
        )
        assert response["event_pipeline"]["reserve_validation"]["attention"]
        assert saved == original
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("discard", ["replaced_state", "changed_route", "stale_slot"])
def test_discarded_results_cannot_clear_an_existing_shared_fault(settings, clock, discard):
    engine = Orchestrator(settings)
    state, response, _, now = route_fixture()
    engine.features.tokens[state.mint] = state
    selected = {state.mint: copy.copy(state)}
    originals = {state.mint: state}
    for tick in (0, 15, 30):
        clock.tick = tick
        with engine._reserve_validation.batch("learning") as batch:
            batch.rejected("pump_curve", failure())
    before = status(engine._reserve_validation)
    if discard == "replaced_state":
        engine.features.tokens[state.mint] = copy.copy(state)
    elif discard == "changed_route":
        state.curve_address = "new-route"
    else:
        response["slot"] = 1
    try:
        engine._apply_learning_reserve_result(selected, originals, response, now)
        assert status(engine._reserve_validation) == before
        assert engine._learning_refresh_status["accepted_routes"] == 0
        assert engine._learning_refresh_status["checkpoint_updates"] == 0
        assert not engine._learning_invalid_routes
        assert not engine.learning.observations
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("accepted_first", [False, True])
def test_mixed_batch_keeps_the_fault_in_either_route_order(clock, accepted_first):
    tracker = ReserveValidationHealth()
    for tick in (0, 15, 30):
        clock.tick = tick
        with tracker.batch("watchdog") as batch:
            if accepted_first:
                batch.accepted("pump_swap")
            batch.rejected("pump_swap", failure())
            if not accepted_first:
                batch.accepted("pump_swap")
    assert status(tracker)["attention"]
    assert status(tracker)["components"][3]["failed_batches"] == 3
    detached = status(tracker)
    detached["components"][3]["state"] = "verified"
    assert status(tracker)["components"][3]["state"] == "blocked"


def test_concurrent_sources_and_readers_keep_complete_bounded_snapshots(clock):
    tracker = ReserveValidationHealth()
    for tick in (0, 15, 30):
        clock.tick = tick
        for source in ("learning", "watchdog"):
            with tracker.batch(source) as batch:
                batch.rejected("pump_curve", failure())

    # Frozen time keeps this deterministic. There is no sleep or live profiling.
    def writer(source):
        for _ in range(100):
            with tracker.batch(source) as batch:
                batch.rejected("pump_curve", failure())
                batch.accepted("pump_swap")

    def reader():
        for _ in range(100):
            current = status(tracker)
            assert current["attention"]
            assert len(current["components"]) == 4
            for row in current["components"]:
                if row["venue"] == "pump_curve":
                    assert row["state"] == "blocked"
                    assert row["account_type"] == "FeeConfig"
                    assert 3 <= row["failed_batches"] <= 103
                else:
                    assert row["state"] in {"not_observed", "verified"}
                    assert row["failed_batches"] == 0 and row["reason"] is None
            assert all(
                0 <= code < 128 for code in reserve_health.compact_validation_health(current)
            )
            json.dumps(current, allow_nan=False)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(writer, source) for source in ("learning", "watchdog")]
        futures.append(pool.submit(reader))
        for future in futures:
            future.result(timeout=10)
    assert [row["failed_batches"] for row in status(tracker)["components"]] == [103, 0, 103, 0]


@pytest.mark.parametrize("record_health", [False, True])
def test_successful_five_route_batch_keeps_real_learning_and_durable_evidence(
    settings, record_health
):
    class NoHealth(ReserveValidationHealth):
        @contextmanager
        def batch(self, source):
            yield reserve_health.ValidationBatch()

    engine = Orchestrator(settings)
    if not record_health:
        engine._reserve_validation = NoHealth()
    fixtures = [
        route_fixture("pump_curve" if seed % 2 else "pump_swap", seed=seed) for seed in range(1, 6)
    ]
    states = {state.mint: state for state, _, _, _ in fixtures}
    response = {
        "slot": 101,
        "accounts": {
            address: account
            for _, response, _, _ in fixtures
            for address, account in response["accounts"].items()
        },
    }
    now = fixtures[-1][3]
    engine.features.tokens.update(states)
    originals = copy.deepcopy(states)
    try:
        for state in states.values():
            decision = learning_decision(now - timedelta(seconds=301), state.mint).model_copy(
                update={"configuration_fingerprint": engine.learning.configuration_fingerprint()}
            )
            assert engine.learning.register(
                decision, make_state(state.mint), live=True, evaluation_actionable=True
            )
        started = time.perf_counter()
        engine._apply_learning_reserve_result(
            {mint: copy.copy(s) for mint, s in states.items()}, states, response, now
        )
        elapsed = time.perf_counter() - started
        counts = engine.learning.collection_diagnostics.snapshot()["counts"]
        assert counts["discovery_300"]["usable"] == counts["policy_300"]["usable"] == 5
        saved = {
            mint: engine.learning.observations[mint].checkpoints["300"].model_dump_json()
            for mint in states
        }
        assert all(
            engine.learning.observations[mint].checkpoints["300"].net_return is not None
            for mint in states
        )
        reloaded = LearningEngine(engine.database, settings)
        assert saved == {
            mint: reloaded.observations[mint].checkpoints["300"].model_dump_json()
            for mint in states
        }
        updates = engine._learning_refresh_status["checkpoint_updates"]
        assert updates > 0
        engine._apply_learning_reserve_result(
            {mint: copy.copy(s) for mint, s in states.items()}, states, response, now
        )
        assert engine._learning_refresh_status["checkpoint_updates"] == updates
        assert engine.features.tokens == originals
        print(f"Five real routes: health={record_health}, seconds={elapsed:.6f}, updates={updates}")
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
