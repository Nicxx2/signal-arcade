import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event, get_ident

import pytest
from signal_arcade.orchestrator import _SNAPSHOT_WORK, _snapshot_part
from test_probe_retention import engine  # noqa: F401


def test_snapshot_age_includes_worker_assembly(engine, monkeypatch):  # noqa: F811
    observed = []

    def snapshot():
        observed.append(datetime.now(UTC))
        return {}

    monkeypatch.setattr(engine, "snapshot", snapshot)
    response = asyncio.run(engine._refresh_snapshot())
    assert datetime.fromisoformat(response["snapshot_generated_at"]) <= observed[0]
    assert response["snapshot_age_seconds"] >= 0


@pytest.mark.parametrize("invalidated", [False, True])
def test_saved_snapshot_age_measures_capture_not_cache_completion(engine, monkeypatch, invalidated):  # noqa: F811
    import time

    captured_at = datetime.now(UTC) - timedelta(seconds=120)
    engine._ui_snapshot_cache = (time.monotonic(), captured_at, {})
    if invalidated:
        engine.invalidate_snapshot_cache()
    recorded = []
    monkeypatch.setattr(engine.diagnostics, "collect", lambda **kwargs: recorded.append(kwargs))
    engine._collect_diagnostics()
    age = recorded[0]["gauges"]["snapshot_age"]
    assert 120 <= age < 125
    response = engine._snapshot_cache_response(engine._ui_snapshot_cache)
    assert response["snapshot_age_seconds"] == pytest.approx(age, abs=1)


@pytest.mark.parametrize("future", [False, True])
def test_missing_or_future_capture_does_not_invent_snapshot_age(engine, monkeypatch, future):  # noqa: F811
    if future:
        engine._ui_snapshot_cache = (0.0, datetime.now(UTC) + timedelta(hours=1), {})
    recorded = []
    monkeypatch.setattr(engine.diagnostics, "collect", lambda **kwargs: recorded.append(kwargs))
    engine._collect_diagnostics()
    assert recorded[0]["gauges"]["snapshot_age"] == (0 if future else None)


@pytest.mark.parametrize("enabled", [False, True])
def test_real_snapshot_sections_are_observational_and_optional(engine, enabled):  # noqa: F811
    engine.diagnostics.enabled = enabled
    snapshot = asyncio.run(engine._refresh_snapshot())
    assert snapshot["portfolio"]["positions"] == []
    assert _SNAPSHOT_WORK.get() is None
    for name in ("portfolio", "history", "tokens", "decisions", "learning", "advisory", "other"):
        assert ("snapshot_" + name in engine.diagnostics.runtime_work_since_boot) is enabled
    if enabled:
        phases = engine.diagnostics.runtime_evidence.slow["snapshot"]["phases"]
        assert phases["snapshot_learning"] == round(
            engine.diagnostics.runtime_work_since_boot["snapshot_learning"][1], 6
        )
        assert {"snapshot_cpu", "snapshot_wait", "snapshot_lock_wait"} <= phases.keys()
    assert not engine.learning.active_skill_versions


@pytest.mark.parametrize("cancel", [False, True])
def test_snapshot_measurements_join_the_worker_and_publish_on_owner(engine, monkeypatch, cancel):  # noqa: F811
    entered, release = Event(), Event()
    owner = get_ident()
    observations = []
    original = engine.diagnostics.observe_runtime_work

    def observe(timing):
        assert get_ident() == owner
        observations.extend(timing)
        original(timing)

    def slow():
        entered.set()
        assert release.wait(3)
        if not cancel:
            raise ValueError("snapshot failure")
        return {}

    monkeypatch.setattr(engine.diagnostics, "observe_runtime_work", observe)
    monkeypatch.setattr(engine, "snapshot", lambda: _snapshot_part("snapshot_learning", slow))

    async def run():
        task = asyncio.create_task(engine._refresh_snapshot())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            if cancel:
                task.cancel()
                await asyncio.sleep(0)
            assert engine._event_lock.locked()
            assert not observations
            assert "snapshot" not in engine.diagnostics.runtime_evidence.slow
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError if cancel else ValueError):
            await task
        assert not engine._event_lock.locked()
        assert _SNAPSHOT_WORK.get() is None
        assert engine._ui_snapshot_cache is None
        assert observations.count("snapshot_learning") == 1
        assert engine.diagnostics.runtime_evidence.slow["snapshot"]["outcome"] == (
            "cancelled" if cancel else "error"
        )

    asyncio.run(run())


def test_part_measurement_preserves_return_identity_and_accumulates():
    parts = {}
    token = _SNAPSHOT_WORK.set(parts)
    value = object()
    try:
        for _ in range(3):
            assert _snapshot_part("snapshot_history", lambda: value) is value
        assert set(parts) == {"snapshot_history"}
        assert parts["snapshot_history"] >= 0
    finally:
        _SNAPSHOT_WORK.reset(token)


def test_runtime_detail_is_bounded_and_yields_to_proof(engine):  # noqa: F811
    from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode

    recorder = engine.diagnostics
    recorder.observe_runtime_work({"snapshot_learning": 1e30, "unknown": 2})
    recorder.observe_runtime_work({"snapshot_history": float("nan"), "snapshot_advisory": -1})
    assert recorder.runtime_work_since_boot == {"snapshot_learning": [1, 1e12, 1e12]}
    for _ in range(8):
        recorder.event({"kind": "proof"})
    engine._record_collection_detail_diagnostics()
    assert all(event["kind"] == "proof" for event in recorder.events)
    assert recorder.dropped == 0
    recorder._take_events(0)
    engine._record_collection_detail_diagnostics()
    detail = next(event for event in recorder.events if event["kind"] == "runtime_work")
    encode(detail, max_payload=MAX_EVENT_PAYLOAD)
    recorder.observe_runtime_work({"snapshot_learning": 2.0})
    assert detail["seconds_since_boot"]["snapshot_learning"] == [1, 1e12, 1e12]
    assert recorder.runtime_work_since_boot["snapshot_learning"][0] == 2
    recorder._take_events(0)
    engine._record_collection_detail_diagnostics()
    assert not recorder.events
