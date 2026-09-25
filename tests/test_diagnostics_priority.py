import json
from types import SimpleNamespace

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_store import MAX_PAYLOAD, encode
from test_diagnostics import interval
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("optional_first", [False, True])
def test_proof_replaces_only_optional_detail(tmp_path, optional_first):
    recorder = DiagnosticsRecorder(tmp_path)
    if optional_first:
        recorder.event({"kind": "storage", "at": 1})
    for index in range(8):
        recorder.event({"kind": "proof", "index": index})
    if not optional_first:
        recorder.event({"kind": "storage", "at": 1})
    assert [item["index"] for item in recorder.events] == list(range(8))
    assert recorder.loss_counts()["event_capacity"] == 1
    assert recorder.loss_counts()["event_categories"]["storage"] == 1


def test_two_publications_stay_bounded_and_report_proof_loss(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    for publication in range(2):
        recorder.event({"kind": "training", "at": publication})
        for index in range(6):
            recorder.event({"kind": "proof", "at": publication, "index": index})
    assert len(recorder.events) == 8
    assert recorder.total_dropped == 6
    assert recorder.lost_event_categories == {"training": 1, "proof": 5, "storage": 0, "other": 0}
    assert recorder.events[-1] == {"kind": "proof", "at": 1, "index": 5}


def test_loss_dimensions_preserve_units_and_detach_interval(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.event({"kind": "proof", "invalid": float("nan")})
    record = interval()
    for _ in range(6):
        recorder.collect(pipeline=record["pipeline"], context={}, gauges={}, skills=[])
    assert recorder.loss_counts()["event_input"] == 1
    assert recorder.loss_counts()["interval_queue"] == 2
    assert recorder.total_dropped == 3
    saved = json.loads(recorder.queue[-1])
    # The interval reports counters at collection; its own eviction is visible next time.
    assert saved["gauges"]["diagnostics_dropped"] == 2
    assert "recording_gap" in saved["flags"]
    encode({k: v for k, v in saved.items() if k != "events"}, max_payload=MAX_PAYLOAD)
    recorder.writer = SimpleNamespace(rejected=2)
    assert recorder.total_dropped == 5
    assert recorder.loss_counts()["writer_intervals"] == 2


def test_disabled_malformed_and_saturated_counts_are_bounded(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path, enabled=False)
    recorder.event({"kind": "proof", "oversize": "x" * 3000})
    assert recorder.total_dropped == 0
    recorder.enabled = True
    for _ in range(8):
        recorder.event({"kind": ["unknown"]})
    recorder.event({"kind": "proof"})
    assert recorder.lost_event_categories["other"] == 1
    recorder.dropped = recorder.loss_reasons["event_input"] = 2**53 - 1
    recorder.lost_event_categories["proof"] = 2**53 - 1
    recorder.event({"kind": "proof", "oversize": "x" * 3000})
    assert recorder.dropped == recorder.loss_reasons["event_input"] == 2**53 - 1
    assert recorder.lost_event_categories["proof"] == 2**53 - 1
    assert len(recorder.events) == 8
    recorder.previous_dropped = recorder.total_dropped
    recorder.collect(pipeline={}, context={}, gauges={}, skills=[])
    assert "recording_gap" in json.loads(recorder.queue[-1])["flags"]
    recorder.collect(pipeline={}, context={}, gauges={}, skills=[])
    assert "recording_gap" not in json.loads(recorder.queue[-1])["flags"]


def test_loss_detail_waits_for_space_and_fits_without_enlarging_intervals(engine):  # noqa: F811
    import random

    from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD

    rng = random.Random(118)  # noqa: S311 -- fixed high-counter compression fixture
    recorder = engine.diagnostics
    for counters in (
        recorder.loss_reasons,
        recorder.lost_event_categories,
        recorder.lost_other_event_kinds,
    ):
        for key in counters:
            counters[key] = rng.randrange(2**52, 2**53)
    recorder.dropped = 2**53 - 1
    for _ in range(8):
        recorder.event({"kind": "proof"})
    engine._record_collection_detail_diagnostics()
    assert all(event["kind"] == "proof" for event in recorder.events)
    recorder.collect(pipeline={}, context={}, gauges={}, skills=[])
    assert "diagnostics_loss_since_boot" not in json.loads(recorder.queue[-1])["gauges"]
    engine._record_collection_detail_diagnostics()
    detail = next(event for event in recorder.events if event["kind"] == "diagnostic_loss")
    assert detail["scope"] == recorder.boot
    assert detail["counts_since_boot"] == recorder.loss_counts()
    assert len(json.dumps(detail, separators=(",", ":")).encode()) <= 2048
    encode(detail, max_payload=MAX_EVENT_PAYLOAD)
    recorder._take_events(0)
    engine._record_collection_detail_diagnostics()
    assert not recorder.events


def test_optional_loss_detail_counts_the_evicted_or_rejected_event_once(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.event({"kind": "collection_selection"})
    for _ in range(7):
        recorder.event({"kind": "proof"})
    recorder.event({"kind": "training_error"})
    assert recorder.loss_counts()["other_event_kinds"] == {"collection_selection": 1}
    assert not recorder.event({"kind": "slow_work"})
    assert recorder.loss_counts()["other_event_kinds"] == {
        "collection_selection": 1,
        "slow_work": 1,
    }
    assert recorder.total_dropped == recorder.loss_counts()["event_capacity"] == 2
    assert recorder.loss_counts()["event_categories"]["other"] == 2
    assert len(recorder.events) == 8
    assert all(item["kind"] in ("proof", "training_error") for item in recorder.events)


@pytest.mark.parametrize("kind", [None, [], {}, 3, "unknown-custom-identifier"])
def test_unknown_loss_types_are_bounded_and_do_not_export_identifiers(tmp_path, kind):
    recorder = DiagnosticsRecorder(tmp_path)
    assert not recorder.event({"kind": kind, "invalid": float("nan")})
    saved = recorder.loss_counts()
    assert saved["other_event_kinds"] == {"unknown": 1}
    saved["other_event_kinds"]["unknown"] = 999
    assert recorder.loss_counts()["other_event_kinds"] == {"unknown": 1}
    assert recorder.total_dropped == 1
    assert "unknown-custom-identifier" not in json.dumps(recorder.loss_counts())


def test_optional_breakdown_saturation_disabled_and_boot_reset(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path, enabled=False)
    recorder.event({"kind": "slow_work", "bad": float("nan")})
    assert recorder.loss_counts()["other_event_kinds"] == {}
    recorder.enabled = True
    recorder.lost_other_event_kinds["slow_work"] = 2**53 - 1
    recorder.event({"kind": "slow_work", "bad": float("nan")})
    assert recorder.loss_counts()["other_event_kinds"] == {"slow_work": 2**53 - 1}
    assert recorder.total_dropped == 1
    new = DiagnosticsRecorder(tmp_path)
    assert new.boot != recorder.boot
    assert new.loss_counts()["other_event_kinds"] == {}
