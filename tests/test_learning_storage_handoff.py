"""One fetched batch may cross a brief storage boundary; proof clocks never move."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import signal_arcade.orchestrator as orchestrator_module
from test_learning import make_decision, make_state, policy_episode_for
from test_probe_retention import engine  # noqa: F401
from test_reserve_contract_integration import public_config_route


def prepare(engine, monkeypatch):
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
    return state, response


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "provider",
        "learner",
        "stop",
        "upgrade",
        "sell",
        "lag",
        "route",
        "cancel",
    ],
)
def test_post_fetch_handoff_rechecks_context_and_leaves_market_lock_free(engine, monkeypatch, case):
    state, response = prepare(engine, monkeypatch)
    learner = engine.learning
    market_before = state.last_reserve_at

    async def run():
        entered = asyncio.Event()
        original_wait = engine._storage_idle.wait

        async def tracked_wait():
            entered.set()
            await original_wait()

        monkeypatch.setattr(engine._storage_idle, "wait", tracked_wait)

        async def fetch(*_args, **_kwargs):
            engine._storage_maintenance_active = True
            engine._storage_idle.clear()
            return response

        monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
        task = asyncio.create_task(engine._learning_reserve_tick())
        await entered.wait()
        # Storage/sells can make progress while the already fetched result waits.
        async with engine._event_lock:
            if case == "provider":
                engine.http.solana_generation += 1
            elif case == "learner":
                engine.learning = object()
            elif case == "stop":
                engine.stop_event.set()
            elif case == "upgrade":
                engine._maintenance_requested = True
            elif case == "sell":
                monkeypatch.setattr(engine, "_has_pending_sell", lambda: True)
            elif case == "lag":
                engine.last_processing_lag_seconds = 2
            elif case == "route":
                engine.features.tokens.pop(state.mint)
            elif case == "cancel":
                task.cancel()
            engine._storage_maintenance_active = False
            engine._storage_idle.set()
        if case == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task

    asyncio.run(run())
    assert engine._learning_reserve_in_flight == 0
    assert not engine._event_lock.locked()
    assert state.last_reserve_at == market_before
    assert engine._learning_refresh_status["requests"] == 1
    assert engine._learning_storage_handoff["waited"] == 1
    for row in (learner.observations[state.mint], policy_episode_for(learner, state.mint)):
        assert ("300" in row.checkpoints) is (case == "success")
    if case == "success":
        assert engine._learning_refresh_status["accepted_routes"] == 1
        assert not sum(engine._learning_refresh_status["discarded_by_reason"].values())
    elif case not in {"route", "cancel"}:
        # The final discard is also a deferral, never two independent lost batches.
        assert sum(engine._learning_refresh_status["discarded_by_reason"].values()) == 1
        assert sum(engine._learning_refresh_status["deferred"].values()) == 1


def test_storage_timeout_does_not_starve_cleanup_or_reset_the_deadline(engine, monkeypatch):
    _, response = prepare(engine, monkeypatch)
    monkeypatch.setattr(orchestrator_module, "_LEARNING_STORAGE_HANDOFF_SECONDS", 0.01)

    async def fetch(*_args, **_kwargs):
        engine._storage_maintenance_active = True
        # Intentionally leave a stale set event; it must not produce a spin loop.
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    asyncio.run(engine._learning_reserve_tick())
    assert engine._storage_maintenance_active
    assert engine._learning_storage_handoff == {
        "waited": 1,
        "idle_observed": 0,
        "timed_out": 1,
        "interrupted": 0,
    }
    assert engine._learning_refresh_status["discarded_by_reason"]["maintenance"] == 1
    assert engine._learning_refresh_status["accepted_routes"] == 0
    assert engine._learning_reserve_in_flight == 0


@pytest.mark.parametrize("guard", ["upgrade", "sell", "disabled", "demo", "stop", "provider"])
def test_handoff_never_waits_when_an_existing_priority_guard_blocks(engine, monkeypatch, guard):
    prepare(engine, monkeypatch)
    engine._storage_maintenance_active = True
    generation = engine.http.solana_generation
    if guard == "upgrade":
        engine._maintenance_requested = True
    elif guard == "sell":
        monkeypatch.setattr(engine, "_has_pending_sell", lambda: True)
    elif guard == "disabled":
        engine.settings.learning_reserve_refresh_enabled = False
    elif guard == "demo":
        engine.demo_mode = True
    elif guard == "stop":
        engine.stop_event.set()
    else:
        engine.http.solana_generation += 1
    asyncio.run(engine._await_learning_storage_handoff(engine.learning, generation))
    assert not any(engine._learning_storage_handoff.values())


def test_original_request_clock_reaches_validation_after_handoff(engine, monkeypatch):
    _, response = prepare(engine, monkeypatch)
    sent = []
    applied = []

    async def fetch(*_args, **_kwargs):
        sent.append(datetime.now(UTC))
        return response

    async def handoff(*_args):
        assert not engine._event_lock.locked()

    def apply(_selected, _originals, _response, requested_at, _targets):
        applied.append(requested_at)

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    monkeypatch.setattr(engine, "_await_learning_storage_handoff", handoff)
    monkeypatch.setattr(engine, "_apply_learning_reserve_result", apply)
    asyncio.run(engine._learning_reserve_tick())
    assert len(applied) == 1 and applied[0] <= sent[0]


@pytest.mark.parametrize(
    "entry_age,fetch_delay,handoff_delay,usable,accepted",
    [
        (385, 4.9, 0.1, True, True),
        (385, 4.9, 0.100001, False, True),
        (301, 7.9, 0.1, True, True),
        (301, 7.9, 0.100001, False, False),
    ],
)
def test_storage_wait_counts_toward_real_freshness_and_checkpoint_deadlines(
    engine, monkeypatch, entry_age, fetch_delay, handoff_delay, usable, accepted
):
    state, response, _, requested = public_config_route("pump_curve")
    clock = [requested]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(orchestrator_module, "datetime", Clock)
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    state.last_reserve_at = requested - timedelta(minutes=5)
    original_reserve_time = state.last_reserve_at
    engine.features.tokens[state.mint] = state
    decision = make_decision(requested - timedelta(seconds=entry_age), state.mint)
    decision.configuration_fingerprint = engine.learning.configuration_fingerprint()
    assert engine.learning.register(
        decision, make_state(state.mint), live=True, evaluation_actionable=True
    )

    async def fetch(*_args, **_kwargs):
        clock[0] = requested + timedelta(seconds=fetch_delay)
        engine._storage_maintenance_active = True
        engine._storage_idle.clear()
        return response

    async def idle():
        assert not engine._event_lock.locked()
        clock[0] += timedelta(seconds=handoff_delay)
        engine._storage_maintenance_active = False
        engine._storage_idle.set()

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    monkeypatch.setattr(engine._storage_idle, "wait", idle)
    asyncio.run(engine._learning_reserve_tick())
    assert engine._learning_storage_handoff["idle_observed"] == 1
    assert engine._learning_refresh_status["accepted_routes"] == int(accepted)
    for row in (
        engine.learning.observations[state.mint],
        policy_episode_for(engine.learning, state.mint),
    ):
        checkpoint = row.checkpoints.get("300")
        if not accepted:
            assert checkpoint is None
        else:
            assert checkpoint.observed_at == clock[0]
            assert (checkpoint.net_return is not None) is usable
            if not usable:
                assert checkpoint.missing_reason == "checkpoint_window_elapsed"
    assert state.last_reserve_at == original_reserve_time
    assert not engine.broker.positions


def test_storage_release_wakes_both_snapshot_and_rpc_waiters(engine, monkeypatch):
    prepare(engine, monkeypatch)
    engine._storage_maintenance_active = True
    refreshed = []

    async def refresh():
        refreshed.append(True)
        return {"ready": True}

    monkeypatch.setattr(engine, "_refresh_snapshot", refresh)

    async def run():
        snapshot = asyncio.create_task(engine._refresh_snapshot_after_storage())
        handoff = asyncio.create_task(
            engine._await_learning_storage_handoff(engine.learning, engine.http.solana_generation)
        )
        await asyncio.sleep(0)
        assert not snapshot.done() and not handoff.done()
        assert not engine._event_lock.locked()
        engine._storage_maintenance_active = False
        engine._storage_idle.set()
        async with asyncio.timeout(0.2):
            assert await snapshot == {"ready": True}
            await handoff

    asyncio.run(run())
    assert refreshed == [True]
    assert engine._learning_storage_handoff["idle_observed"] == 1
