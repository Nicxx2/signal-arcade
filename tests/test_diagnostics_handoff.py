"""End-to-end bounded reporting failures cannot masquerade as durable proof."""

import asyncio
import json
import time
from threading import Event

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_store import DiagnosticsStore, read_events
from signal_arcade.diagnostics_worker import DiagnosticsWriter
from test_publication_backlog import collect, reports


@pytest.mark.parametrize("protected_at", [0, 1, 2, 3])
def test_optional_overflow_preserves_proof_and_order(tmp_path, protected_at):
    recorder = DiagnosticsRecorder(tmp_path)
    for at in range(8):
        if at == protected_at:
            recorder.publication(reports(at=at, proofs=6))
        collect(recorder)
    records = [json.loads(raw) for raw in recorder.queue]
    assert [r["seq"] for r in records] == sorted(r["seq"] for r in records)
    assert len(records) == 4
    assert sum(len(r["events"]) for r in records) == 7
    with_store = DiagnosticsStore(tmp_path)
    try:
        for record in records:
            assert with_store.append(record)
    finally:
        with_store.close()
    assert len(read_events(tmp_path, before=records[-1]["end"] + 1)) == 7
    assert recorder.loss_counts()["handoff_event_categories"]["proof"] == 0


def test_all_protected_overflow_counts_embedded_events_once(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    for at in range(5):
        recorder.publication(reports(at=at, proofs=6))
        collect(recorder)
    assert recorder.total_dropped == 1
    assert recorder.loss_counts()["handoff_event_categories"] == {
        "training": 1,
        "proof": 6,
        "storage": 0,
        "other": 0,
    }
    collect(recorder)  # An empty incoming interval cannot evict another proof group.
    assert [json.loads(raw)["seq"] for raw in recorder.queue] == [1, 2, 3, 4]
    assert recorder.total_dropped == 2
    assert recorder.loss_counts()["handoff_event_categories"]["proof"] == 6


@pytest.mark.parametrize("bad", [float("nan"), object(), "x" * 200_000])
def test_failed_serialization_keeps_original_pending_report(tmp_path, bad):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.publication(reports(at=17, proofs=6))
    original = json.dumps(recorder.publications[0][1])
    recorder.collect(pipeline={}, context={}, gauges={"bad": bad}, skills=[])
    assert not recorder.queue
    assert json.dumps(recorder.publications[0][1]) == original
    assert recorder.pending_publication_events == 7
    assert recorder.loss_counts()["interval_input"] == 1
    collect(recorder)
    assert recorder.pending_publication_events == 0
    assert len(json.loads(recorder.queue[0])["events"]) == 7


def test_stop_accounts_for_all_pending_stages_without_double_counting(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.publication(reports(proofs=2))
    collect(recorder)
    recorder.publication(reports(proofs=3))
    recorder.event({"kind": "proof"})
    asyncio.run(recorder.stop())
    assert recorder.loss_counts()["handoff_event_categories"]["proof"] == 2
    assert recorder.loss_counts()["event_categories"]["proof"] == 4
    counts = recorder.loss_counts()
    asyncio.run(recorder.stop())
    assert counts == recorder.loss_counts()


@pytest.mark.parametrize("failure", ["before", "after", "status", "unknown", "uncommitted"])
def test_writer_distinguishes_rejection_from_post_commit_failure(tmp_path, monkeypatch, failure):
    import signal_arcade.diagnostics_worker as worker

    complete = Event()
    original = DiagnosticsStore

    class Store(original):
        def append(self, record):
            if failure == "uncommitted":
                self.connection.execute(
                    "INSERT INTO intervals VALUES (0,?,?,?,?,?)",
                    (record["boot"], record["seq"], record["start"], record["end"], b"{}"),
                )
                raise OSError("rollback outcome unavailable")
            if failure in {"before", "unknown"}:
                raise OSError("private error")
            result = super().append(record)
            if failure == "after":
                raise OSError("private checkpoint error")
            return result

        def contains_interval(self, record):
            if failure == "unknown":
                raise OSError("cannot check")
            return super().contains_interval(record)

        def status(self):
            if failure == "status" and self.writes:
                raise OSError("private status error")
            return super().status()

    monkeypatch.setattr(worker, "DiagnosticsStore", Store)
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.publication(reports(proofs=2))
    collect(recorder)
    writer = DiagnosticsWriter(tmp_path)
    writer.allowed.set()
    writer.thread.start()
    try:
        assert writer.offer(recorder.queue[0])
        deadline = time.monotonic() + 5
        while writer.status.get("state") != "paused_error" and time.monotonic() < deadline:
            complete.wait(0.01)
        assert writer.status["state"] == "paused_error"
        assert writer.rejected == int(failure == "before")
        assert writer.loss_events()["proof"] == (2 if failure == "before" else 0)
        assert writer.uncertain == int(failure in {"unknown", "uncommitted"})
        assert (writer.last_saved_monotonic is not None) == (failure in {"after", "status"})
        assert "private" not in json.dumps(writer.status)
    finally:
        writer.request_stop()
        writer.thread.join(5)
    assert not writer.thread.is_alive()
    assert not writer.offer(recorder.queue[0])


def test_stopping_blocked_writer_counts_inflight_and_queued(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.publication(reports(proofs=2))
    collect(recorder)
    raw = recorder.queue[0]
    writer = DiagnosticsWriter(tmp_path)
    writer.thread.start()
    try:
        assert writer.offer(raw)
        deadline = time.monotonic() + 5
        while not writer.busy and time.monotonic() < deadline:
            Event().wait(0.01)
        assert writer.busy
        assert writer.offer(raw)
    finally:
        writer.request_stop()
        writer.thread.join(5)
    assert writer.rejected == 2
    assert writer.loss_events()["proof"] == 4


def test_all_loss_dimensions_fit_existing_payload_limits(tmp_path):
    import random
    from types import SimpleNamespace

    from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode

    rng = random.Random(907)  # noqa: S311 -- deterministic worst-case counter payload
    recorder = DiagnosticsRecorder(tmp_path)
    for counts in (
        recorder.loss_reasons,
        recorder.lost_event_categories,
        recorder.lost_handoff_events,
        recorder.lost_other_event_kinds,
    ):
        for key in counts:
            counts[key] = rng.randrange(2**52, 2**53)
    recorder.writer = SimpleNamespace(
        rejected=rng.randrange(2**52, 2**53),
        uncertain=rng.randrange(2**52, 2**53),
        loss_events=lambda: {
            key: rng.randrange(2**52, 2**53) for key in recorder.lost_handoff_events
        },
    )
    event = {
        "kind": "diagnostic_loss",
        "scope": recorder.boot,
        "at": 1_800_000_000.123,
        "counts_since_boot": recorder.loss_counts(),
    }
    assert len(json.dumps(event, separators=(",", ":")).encode()) <= 2048
    encode(event, max_payload=MAX_EVENT_PAYLOAD)


def test_uncertain_write_marks_a_gap_without_claiming_confirmed_loss(tmp_path):
    from types import SimpleNamespace

    recorder = DiagnosticsRecorder(tmp_path)
    recorder.writer = SimpleNamespace(rejected=0, uncertain=1)
    recorder.collect(pipeline={}, context={}, gauges={}, skills=[])
    assert "recording_gap" in json.loads(recorder.queue[0])["flags"]
    assert recorder.total_dropped == 0
