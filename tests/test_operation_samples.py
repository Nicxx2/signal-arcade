"""Slow-operation evidence is coherent, task-local and has no execution authority."""

import asyncio
from threading import Event

import pytest
from signal_arcade.diagnostics import _OPERATION, DiagnosticsRecorder
from signal_arcade.orchestrator import _timed_to_thread


def test_nested_operations_restore_owner_and_do_not_mix_snapshot_and_market(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    market = recorder.begin_operation("market")
    recorder.observe_duration("event_features", 2)
    snapshot = recorder.begin_operation("snapshot")
    recorder.observe_runtime_work({"snapshot_learning": 4})
    recorder.observe_duration("event_ai", 9)  # Not a snapshot dimension.
    recorder.finish_operation(snapshot, "complete")
    recorder.observe_duration("event_features", 3)
    recorder.observe_work_detail("decision", {"decision_lock": [1, 7, 7]})
    recorder.finish_operation(market, "complete")
    assert _OPERATION.get() is None
    assert recorder.runtime_evidence.slow["snapshot"]["phases"] == {"snapshot_learning": 4}
    assert recorder.runtime_evidence.slow["market"]["phases"] == {
        "event_features": 5,
        "decision_lock": 7,
    }


def test_overlapping_tasks_keep_their_own_parts(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    samples = []
    recorder.observe_slow_work = lambda lane, started, parts, outcome: samples.append(dict(parts))

    async def run():
        async def task(value):
            operation = recorder.begin_operation("market")
            recorder.observe_duration("event_features", value)
            await asyncio.sleep(0)
            recorder.observe_duration("event_ai", value)
            recorder.finish_operation(operation, "complete")

        await asyncio.gather(task(1), task(2))
        assert _OPERATION.get() is None

    asyncio.run(run())
    assert samples == [{"event_features": 1, "event_ai": 1}, {"event_features": 2, "event_ai": 2}]


@pytest.mark.parametrize("ending", ["success", "error", "cancel"])
def test_ai_timing_retains_worker_ownership_and_records_only_after_join(tmp_path, ending):
    recorder = DiagnosticsRecorder(tmp_path)
    entered, release, finished = Event(), Event(), Event()
    value = object()

    def worker():
        entered.set()
        assert release.wait(3)
        finished.set()
        if ending == "error":
            raise ValueError("worker failed")
        return value

    async def run():
        async def measured():
            operation = recorder.begin_operation("market")
            outcome = "error"
            try:
                result = await _timed_to_thread(recorder, "event_ai", worker)
                outcome = "complete"
                return result
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            finally:
                recorder.finish_operation(operation, outcome)

        task = asyncio.create_task(measured())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            if ending == "cancel":
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
            assert not recorder.runtime_evidence.slow
            assert not task.done()
        finally:
            release.set()
        if ending == "success":
            assert await task is value
        else:
            with pytest.raises(ValueError if ending == "error" else asyncio.CancelledError):
                await task
        assert finished.is_set() and _OPERATION.get() is None
        saved = recorder.runtime_evidence.slow["market"]
        assert (
            saved["outcome"]
            == {"success": "complete", "error": "error", "cancel": "cancelled"}[ending]
        )
        assert set(saved["phases"]) == {"event_ai_cpu", "event_ai_wait"}

    asyncio.run(run())


def test_disabled_or_failed_reporting_never_replaces_result(tmp_path, monkeypatch):
    recorder = DiagnosticsRecorder(tmp_path, enabled=False)
    assert recorder.begin_operation("market") is None
    recorder.finish_operation(None, "complete")
    assert not recorder.runtime_evidence.slow
    recorder.enabled = True
    operation = recorder.begin_operation("market")
    monkeypatch.setattr(recorder, "observe_slow_work", lambda *args: 1 / 0)
    recorder.finish_operation(operation, "complete")
    assert _OPERATION.get() is None and recorder.loss_counts()["reporting_error"] == 1


def test_dispatch_counts_are_bounded_detached_and_optional(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.ai_dispatch_since_boot["dispatch"] = 2**53 - 1
    recorder.observe_ai_dispatch(True)
    recorder.observe_ai_dispatch(False)
    assert recorder.ai_dispatch_since_boot == {"dispatch": 2**53 - 1, "not_due": 1}
    saved = recorder.status()["ai_dispatch_since_boot"]
    recorder.enabled = False
    recorder.observe_ai_dispatch(False)
    recorder.ai_dispatch_since_boot["not_due"] = 2
    assert saved["not_due"] == 1
