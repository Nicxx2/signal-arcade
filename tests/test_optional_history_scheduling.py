"""Paced optional cleanup preserves ownership and accurate committed-row counts."""

# ruff: noqa: F811 -- shared fixture

import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
import signal_arcade.orchestrator as module
from test_learning import make_decision, make_state, policy_episode_for
from test_probe_retention import engine  # noqa: F401
from test_reserve_contract_integration import public_config_route


def test_categories_rotate_and_deferred_work_is_paced(engine, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    calls = []

    def prune(category, **kwargs):
        calls.append((category, kwargs["deadline"]))
        if category == "incidents":
            return {"removed": 0, "completed": 0, "deferred": 1, "work_remaining": 1}
        return {"removed": 3, "completed": 1, "deferred": 0, "work_remaining": 0}

    monkeypatch.setattr(engine.database, "prune_optional_history", prune)
    removed, phases = {"incidents": 0, "ai_assessments": 0}, {}

    async def scenario():
        for at in (100, 100.25, 104.99, 105, 110):
            clock[0] = at
            await engine._prune_optional_history(Event(), removed, phases)

    asyncio.run(scenario())
    assert calls == [("incidents", 100.05), ("ai_assessments", 105.05), ("incidents", 110.05)]
    assert removed == {"incidents": 0, "ai_assessments": 3}
    assert engine._storage_optional_history_status["incidents"]["completed_at"] is None
    assert engine._storage_optional_history_status["ai_assessments"]["completed_at"] is not None
    assert engine._storage_optional_history_due["ai_assessments"] == 165


@pytest.mark.parametrize("reason", ["cancelled", "maintenance", "market", "sticky_yield"])
def test_optional_work_always_yields_even_if_main_cleanup_is_urgent(engine, monkeypatch, reason):
    cancelled = Event()
    if reason == "cancelled":
        cancelled.set()
    elif reason == "maintenance":
        engine._maintenance_requested = True
    elif reason == "market":
        monkeypatch.setattr(engine, "_storage_market_path_busy", lambda: True)
    else:
        engine._storage_market_yield_requested.set()
        engine._event_batches_in_flight = 1
    monkeypatch.setattr(
        engine.database,
        "prune_optional_history",
        lambda *_a, **_k: pytest.fail("optional work must yield"),
    )
    removed = {"incidents": 0, "ai_assessments": 0}
    asyncio.run(engine._prune_optional_history(cancelled, removed, {}))
    assert not engine._storage_optional_history_status
    assert removed == {"incidents": 0, "ai_assessments": 0}


def test_executor_wait_does_not_refresh_the_sql_budget(engine, monkeypatch):
    original = module._joined_to_thread
    observed = []

    async def dispatched(function, *args, **kwargs):
        await asyncio.sleep(0.07)
        return await original(function, *args, **kwargs)

    monkeypatch.setattr(module, "_joined_to_thread", dispatched)
    engine.database._conn.set_trace_callback(observed.append)
    asyncio.run(engine._prune_optional_history(Event(), {"incidents": 0, "ai_assessments": 0}, {}))
    assert not observed
    status = engine._storage_optional_history_status["incidents"]
    assert status["deferred"] == 1 and status["completed"] == 0


def test_quiet_loop_services_optional_work_without_rerunning_primary_cleanup(engine, monkeypatch):
    engine.last_maintenance_at = datetime.now(UTC)
    engine._storage_maintenance_requested = False
    calls = []

    def prune(category, **_kwargs):
        calls.append(category)
        assert engine._storage_maintenance_active and not engine._storage_idle.is_set()
        return {"removed": 2, "completed": 1, "deferred": 0, "work_remaining": 0}

    monkeypatch.setattr(engine.database, "prune_optional_history", prune)
    monkeypatch.setattr(
        engine, "_run_storage_maintenance", lambda *_a: pytest.fail("primary work was not due")
    )
    waits = []

    async def wait(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    asyncio.run(engine._storage_loop())
    assert calls == ["incidents"] and waits == [15, 5]
    assert engine._storage_removed_total["incidents"] == 2
    assert engine._storage_diagnostic_removed["incidents"] == 2
    assert not engine._storage_maintenance_active and engine._storage_idle.is_set()


def test_repeated_cancellation_joins_worker_and_keeps_committed_counts(engine, monkeypatch):
    entered, release, saw_stop = Event(), Event(), Event()
    stop_checks = []
    monkeypatch.setattr(engine.database, "storage_capacity_stats", lambda: {"live_bytes": 0})
    monkeypatch.setattr(engine.database, "prune_history", lambda *_a, **_k: {})
    monkeypatch.setattr(
        engine.database,
        "prune_retired_decisions",
        lambda **_k: {"retired_decisions": 0, "work_remaining": 0},
    )
    monkeypatch.setattr(engine.database, "enforce_storage_budget", lambda *_a, **_k: {})

    def prune(_category, **kwargs):
        stop_checks.append(kwargs["stop_requested"])
        assert not stop_checks[0]()
        entered.set()
        while not release.wait(0.001):
            if kwargs["stop_requested"]():
                saw_stop.set()
        # Simulates a transaction committed just before cancellation, then descheduled.
        return {"removed": 2, "completed": 1, "deferred": 0, "work_remaining": 0}

    monkeypatch.setattr(engine.database, "prune_optional_history", prune)

    async def scenario():
        task = asyncio.create_task(engine._run_storage_maintenance(datetime.now(UTC)))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert stop_checks[0]()
            task.cancel()
            # Wait for the thread's acknowledgement, not an assumed 40ms CPU slot.
            assert await asyncio.to_thread(saw_stop.wait, 2)
            assert not task.done() and engine._storage_maintenance_active
            assert not engine._storage_idle.is_set()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not engine._storage_maintenance_active and engine._storage_idle.is_set()
        assert engine._storage_maintenance_last_removed["incidents"] == 2
        assert engine._storage_removed_total["incidents"] == 2

    asyncio.run(scenario())


def test_quiet_optional_cleanup_preserves_an_admitted_rpc_and_resumes_afterward(
    engine, monkeypatch
):
    state, response, _, now = public_config_route("pump_curve")
    state.last_reserve_at = now - timedelta(minutes=5)
    engine.features.tokens[state.mint] = state
    decision = make_decision(now - timedelta(seconds=301), state.mint)
    decision.configuration_fingerprint = engine.learning.configuration_fingerprint()
    assert engine.learning.register(
        decision, make_state(state.mint), live=True, evaluation_actionable=True
    )
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    calls = []

    def prune(category, **_kwargs):
        calls.append(category)
        assert engine._learning_reserve_in_flight == 0, "optional cleanup interrupted learning RPC"
        return {"removed": 0, "completed": 1, "deferred": 0, "work_remaining": 0}

    async def fetch(*_args, **_kwargs):
        assert engine._learning_reserve_in_flight == 1
        await engine._run_optional_storage_maintenance()
        assert not engine._storage_maintenance_active and engine._storage_idle.is_set()
        assert not engine._storage_optional_history_status
        return response

    monkeypatch.setattr(engine.database, "prune_optional_history", prune)
    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)

    async def scenario():
        await engine._learning_reserve_tick()
        assert engine._learning_reserve_in_flight == 0
        assert engine._learning_refresh_status["accepted_routes"] == 1
        assert sum(engine._learning_refresh_status["discarded_by_reason"].values()) == 0
        for item in (
            engine.learning.observations[state.mint],
            policy_episode_for(engine.learning, state.mint),
        ):
            assert item.checkpoints["300"].net_return is not None
        await engine._run_optional_storage_maintenance()
        assert calls == ["incidents"]

    asyncio.run(scenario())


def test_quiet_optional_cancellation_keeps_ownership_and_committed_counts(engine, monkeypatch):
    entered, release, saw_stop = Event(), Event(), Event()
    stop_checks = []

    def prune(_category, **kwargs):
        stop_checks.append(kwargs["stop_requested"])
        assert not stop_checks[0]()
        entered.set()
        while not release.wait(0.001):
            if kwargs["stop_requested"]():
                saw_stop.set()
        return {"removed": 2, "completed": 1, "deferred": 0, "work_remaining": 0}

    monkeypatch.setattr(engine.database, "prune_optional_history", prune)

    async def scenario():
        task = asyncio.create_task(engine._run_optional_storage_maintenance())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert stop_checks[0]()
            task.cancel()
            assert await asyncio.to_thread(saw_stop.wait, 2)
            assert not task.done() and engine._storage_maintenance_active
            assert not engine._storage_idle.is_set()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not engine._storage_maintenance_active and engine._storage_idle.is_set()
        assert engine._storage_removed_total["incidents"] == 2
        assert engine._storage_diagnostic_removed["incidents"] == 2

    asyncio.run(scenario())
