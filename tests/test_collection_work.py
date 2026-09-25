"""Measure collection losses without relaxing admission, time or evidence contracts."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import copy
import random
from datetime import datetime, timedelta

import pytest
import signal_arcade.orchestrator as orchestration
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
from test_learning import make_decision, make_state, policy_episode_for
from test_probe_retention import engine  # noqa: F401
from test_reserve_contract_integration import public_config_route


@pytest.mark.parametrize(
    "reason",
    [
        "disabled",
        "demo",
        "maintenance",
        "market_boundary",
        "pending_sell",
        "queue_pressure",
        "processing_lag",
        "market_unhealthy",
        "context_changed",
    ],
)
def test_post_fetch_discard_reasons_are_separate_from_preselection_deferrals(
    engine, monkeypatch, reason
):  # noqa: F811
    state, response, _, _ = public_config_route("pump_curve")
    engine.features.tokens[state.mint] = state
    blocked = [None]
    monkeypatch.setattr(engine, "_learning_reserve_blocked_reason", lambda: blocked[0])
    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", lambda *a, **k: [state.mint])
    monkeypatch.setattr(
        engine, "_apply_learning_reserve_result", lambda *a: pytest.fail("discarded")
    )

    async def fetch(*_a, **_k):
        blocked[0] = reason
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    asyncio.run(engine._learning_reserve_tick())
    status = engine._learning_refresh_status
    assert status["discarded_by_reason"][reason] == 1
    assert sum(status["discarded_by_reason"].values()) == 1
    assert status["deferred"][reason] == 1
    assert status["accepted_routes"] == status["checkpoint_updates"] == 0
    assert "rpc_apply" not in engine.diagnostics.runtime_work_since_boot
    # A subsequent admission failure is a guard check, not another lost RPC batch.
    asyncio.run(engine._learning_reserve_tick())
    assert status["deferred"][reason] == 2
    assert status["discarded_by_reason"][reason] == status["requests"] == 1


@pytest.mark.parametrize("batch_size", [5, 10, 20])
@pytest.mark.parametrize("delay", [4.9, 5.0, 5.000001, 8.000001])
def test_real_batches_preserve_deadlines_and_response_freshness(
    engine, monkeypatch, batch_size, delay
):  # noqa: F811
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    engine.settings.learning_reserve_refresh_batch_size = batch_size
    fixtures = [
        public_config_route("pump_curve" if i % 2 else "pump_swap", i)
        for i in range(1, batch_size + 1)
    ]
    requested = fixtures[-1][3]
    clock = [requested]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(orchestration, "datetime", Clock)
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    states = {state.mint: state for state, *_ in fixtures}
    engine.features.tokens.update(states)
    for state in states.values():
        state.last_reserve_at = requested - timedelta(minutes=5)
        decision = make_decision(requested - timedelta(seconds=385), state.mint)
        decision.configuration_fingerprint = engine.learning.configuration_fingerprint()
        assert engine.learning.register(
            decision, make_state(state.mint), live=True, evaluation_actionable=True
        )
    original = copy.deepcopy(states)

    async def fetch(addresses, **kwargs):
        assert not engine._event_lock.locked()
        assert len(addresses) <= 100 and len(addresses) == len(set(addresses))
        assert kwargs["critical"] is False
        clock[0] = requested + timedelta(seconds=delay)
        return {
            "slot": 101,
            "accounts": {
                address: account
                for _, response, *_ in fixtures
                for address, account in response["accounts"].items()
            },
        }

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    asyncio.run(engine._learning_reserve_tick())
    assert engine._learning_refresh_status["selected_routes"] == batch_size
    assert engine._learning_refresh_status["accepted_routes"] == (batch_size if delay <= 8 else 0)
    for mint in states:
        for item in (engine.learning.observations[mint], policy_episode_for(engine.learning, mint)):
            checkpoint = item.checkpoints.get("300")
            if delay > 8:
                assert checkpoint is None  # Rejected data cannot create an outcome.
            else:
                assert checkpoint.observed_at == clock[0]
                assert (checkpoint.net_return is not None) is (delay <= 5)
                if delay > 5:
                    assert checkpoint.missing_reason == "checkpoint_window_elapsed"
    assert engine.features.tokens == original
    assert not engine.broker.positions


@pytest.mark.parametrize("irregular", [False, True])
def test_complete_runtime_detail_fits_existing_event_limit(engine, irregular):  # noqa: F811
    engine.diagnostics.ai_dispatch_since_boot = {"dispatch": 2**53 - 1, "not_due": 2**53 - 2}
    names = (
        "snapshot_portfolio",
        "snapshot_history",
        "snapshot_tokens",
        "snapshot_decisions",
        "snapshot_learning",
        "snapshot_advisory",
        "snapshot_other",
        "rpc_selection_wait",
        "rpc_request",
        "rpc_result_wait",
        "rpc_storage_handoff",
        "rpc_apply",
    )
    for index, name in enumerate(names):
        engine.diagnostics.observe_runtime_work({name: 12345.678901 / (index + 1)})
        engine.diagnostics.runtime_work_since_boot[name][0] = 2**53 - index - 1
    for index, reason in enumerate(engine._learning_refresh_status["discarded_by_reason"]):
        engine._learning_refresh_status["discarded_by_reason"][reason] = 2**63 - index - 1
    for index, counters in enumerate(engine._learning_maintenance_guards.values()):
        counters.update(deferred=2**53 - index - 1, discarded=2**53 - index - 2)
    for name in engine._learning_storage_handoff:
        engine._learning_storage_handoff[name] = 2**53 - 1
    if irregular:
        rng = random.Random(20260921)  # noqa: S311 - deterministic payload entropy fixture
        for values in engine.diagnostics.runtime_work_since_boot.values():
            values[:] = [rng.randrange(2**52), rng.random() * 1e12, rng.random() * 1e5]
        for source in engine._learning_maintenance_guards.values():
            source.update(deferred=rng.randrange(2**52), discarded=rng.randrange(2**51))
    engine._record_collection_detail_diagnostics()
    events = [e for e in engine.diagnostics.events if e["kind"] == "runtime_work"]
    for event in events:
        encode(event, max_payload=MAX_EVENT_PAYLOAD)
    assert {
        name: values for event in events for name, values in event["seconds_since_boot"].items()
    } == engine.diagnostics.runtime_work_since_boot
    assert sum("storage_handoff_since_boot" in event for event in events) == 1
    assert engine.diagnostics.dropped == 0
