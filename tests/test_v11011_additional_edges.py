"""Post-rollout edge checks with temporary data and no live service interaction."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import copy
from threading import Event, get_ident

import pytest
import signal_arcade.orchestrator as orchestration
from signal_arcade.orchestrator import _SNAPSHOT_WORK, _snapshot_part
from test_probe_retention import engine  # noqa: F401
from test_reserve_contract_integration import public_config_route


def reserve_fixture(engine, monkeypatch):
    state, response, _, _ = public_config_route("pump_curve")
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    engine.features.tokens[state.mint] = state
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", lambda *a, **k: [state.mint])
    return state, response


@pytest.mark.parametrize("change", ["disabled", "demo", "maintenance", "context_changed"])
def test_actual_state_change_during_rpc_cannot_apply_response(engine, monkeypatch, change):
    state, response = reserve_fixture(engine, monkeypatch)
    original = copy.deepcopy(state)
    monkeypatch.setattr(
        engine, "_apply_learning_reserve_result", lambda *a: pytest.fail("unsafe application")
    )

    async def fetch(*_a, **_k):
        assert not engine._event_lock.locked()
        if change == "disabled":
            engine.settings.learning_reserve_refresh_enabled = False
        elif change == "demo":
            engine.demo_mode = True
        elif change == "maintenance":
            engine._maintenance_requested = True
        else:
            engine.learning = copy.copy(engine.learning)
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    asyncio.run(engine._learning_reserve_tick())
    status = engine._learning_refresh_status
    assert status["requests"] == 1
    assert status["discarded_by_reason"][change] == status["deferred"][change] == 1
    assert status["accepted_routes"] == status["checkpoint_updates"] == 0
    assert engine.features.tokens[state.mint] == original
    assert not engine.broker.positions


@pytest.mark.parametrize("worker_fails", [False, True])
def test_repeated_snapshot_cancellation_keeps_next_refresh_out_until_worker_joins(
    engine, monkeypatch, worker_fails
):
    entered, release, competitor_entered = Event(), Event(), Event()
    owner = get_ident()
    seen = []
    original = engine.diagnostics.observe_runtime_work

    def observe(parts):
        assert get_ident() == owner
        seen.append(dict(parts))
        original(parts)

    def first_snapshot():
        def work():
            entered.set()
            assert release.wait(5)
            if worker_fails:
                raise ValueError("late worker failure")
            return {}

        return _snapshot_part("snapshot_learning", work)

    def next_snapshot():
        competitor_entered.set()
        return _snapshot_part("snapshot_history", lambda: {"marker": "next"})

    monkeypatch.setattr(engine.diagnostics, "observe_runtime_work", observe)
    monkeypatch.setattr(engine, "snapshot", first_snapshot)

    async def scenario():
        first = asyncio.create_task(engine._refresh_snapshot())
        second = None
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            for _ in range(3):
                first.cancel()
                await asyncio.sleep(0)
            monkeypatch.setattr(engine, "snapshot", next_snapshot)
            second = asyncio.create_task(engine._refresh_snapshot())
            await asyncio.sleep(0.01)
            assert engine._event_lock.locked()
            assert not first.done() and not second.done()
            assert not competitor_entered.is_set() and not seen
            assert engine._ui_snapshot_cache is None
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert second is not None
        result = await asyncio.wait_for(second, 3)
        assert result["marker"] == "next"
        assert [set(parts) for parts in seen] == [{"snapshot_learning"}, {"snapshot_history"}]
        assert not engine._event_lock.locked()
        assert _SNAPSHOT_WORK.get() is None

    asyncio.run(scenario())


def test_cancelled_browser_cannot_cancel_shared_snapshot_or_duplicate_measurements(
    engine, monkeypatch
):
    entered, release = Event(), Event()
    calls = []

    def snapshot():
        def work():
            calls.append(1)
            entered.set()
            assert release.wait(5)
            return {"marker": "shared"}

        return _snapshot_part("snapshot_learning", work)

    monkeypatch.setattr(engine, "snapshot", snapshot)

    async def scenario():
        browsers = [asyncio.create_task(engine.snapshot_view()) for _ in range(3)]
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            browsers[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await browsers[0]
            assert engine._ui_snapshot_task is not None
            assert not engine._ui_snapshot_task.done()
            assert engine._event_lock.locked()
            assert not engine.diagnostics.runtime_work_since_boot
        finally:
            release.set()
        results = await asyncio.wait_for(asyncio.gather(*browsers[1:]), 3)
        assert all(row["marker"] == "shared" for row in results)
        assert results[0]["snapshot_generated_at"] == results[1]["snapshot_generated_at"]
        assert calls == [1]
        assert engine.diagnostics.runtime_work_since_boot["snapshot_learning"][0] == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["request", "apply", "apply_failure"])
def test_rpc_cancellation_preserves_worker_ownership_and_reports_only_completed_phases(
    engine, monkeypatch, phase
):
    _, response = reserve_fixture(engine, monkeypatch)
    entered, release = Event(), Event()
    owner = get_ident()
    original = engine.diagnostics.observe_runtime_work

    def observe(parts):
        assert get_ident() == owner
        original(parts)

    async def fetch(*_a, **_k):
        if phase == "request":
            entered.set()
            await asyncio.Event().wait()
        return response

    def apply(*_a):
        assert phase != "request"
        entered.set()
        assert release.wait(5)
        # A cancelled async caller must retain ownership until this real commit finishes.
        engine.database.set_setting("edge_worker_committed", True)
        if phase == "apply_failure":
            raise ValueError("late apply failure")

    monkeypatch.setattr(engine.diagnostics, "observe_runtime_work", observe)
    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    monkeypatch.setattr(engine, "_apply_learning_reserve_result", apply)

    async def scenario():
        task = asyncio.create_task(engine._learning_reserve_tick())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            for _ in range(3):
                task.cancel()
                await asyncio.sleep(0)
            if phase != "request":
                assert not task.done()
                assert engine._event_lock.locked()
                assert "rpc_apply" not in engine.diagnostics.runtime_work_since_boot
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not engine._event_lock.locked()
        timings = engine.diagnostics.runtime_work_since_boot
        assert timings["rpc_request"][0] == 1
        assert ("rpc_apply" in timings) is (phase != "request")
        assert engine.database.get_setting("edge_worker_committed", False) is (phase != "request")
        assert engine._learning_refresh_status["last_completed_at"] is None
        assert sum(engine._learning_refresh_status["discarded_by_reason"].values()) == 0

    asyncio.run(scenario())


def test_runtime_counts_saturate_ignore_invalid_numbers_and_stop_when_disabled(engine):
    recorder = engine.diagnostics
    recorder.runtime_work_since_boot["rpc_apply"] = [2**53 - 1, 1e12, 1e12]
    recorder.observe_runtime_work({"rpc_apply": 1e308})
    assert recorder.runtime_work_since_boot["rpc_apply"] == [2**53 - 1, 1e12, 1e12]
    for invalid in (float("nan"), float("inf"), -float("inf"), -1.0):
        recorder.observe_runtime_work({"rpc_request": invalid})
    assert "rpc_request" not in recorder.runtime_work_since_boot
    recorder.enabled = False
    recorder.observe_runtime_work({"snapshot_learning": 1.0})
    assert set(recorder.runtime_work_since_boot) == {"rpc_apply"}


def test_detail_cadence_includes_exact_boundary_and_resumes_after_proof_pressure(
    engine, monkeypatch
):
    now = [1000.0]
    monkeypatch.setattr(orchestration.time, "monotonic", lambda: now[0])
    recorder = engine.diagnostics
    recorder.observe_runtime_work({"rpc_apply": 1.0})
    engine._record_collection_detail_diagnostics()
    assert [event["kind"] for event in recorder.events] == ["runtime_work", "retention_sample"]
    recorder._take_events(0)
    now[0] += 299.999
    engine._record_collection_detail_diagnostics()
    assert not recorder.events
    now[0] = 1300.0
    for _ in range(8):
        recorder.event({"kind": "proof"})
    engine._record_collection_detail_diagnostics()
    assert len(recorder.events) == 8 and recorder.dropped == 0
    recorder._take_events(0)
    engine._record_collection_detail_diagnostics()
    assert [event["kind"] for event in recorder.events] == ["runtime_work", "retention_sample"]
