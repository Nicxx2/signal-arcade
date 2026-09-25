"""Short publication bursts are retained without increasing writer cadence or authority."""

import json
from types import SimpleNamespace

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_store import DiagnosticsStore, read_events
from test_diagnostics import interval


def reports(at=1, proofs=5):
    return [{"kind": "training", "at": at, "ran": True}] + [
        {"kind": "proof", "at": at, "id": str(index)} for index in range(proofs)
    ]


def collect(recorder):
    recorder.collect(pipeline=interval()["pipeline"], context={}, gauges={}, skills=[])
    return json.loads(recorder.queue[-1])


def test_observed_long_interval_retains_both_publications_and_optional_detail(
    tmp_path, monkeypatch
):
    import signal_arcade.diagnostics as diagnostics

    recorder = DiagnosticsRecorder(tmp_path)
    clock = [recorder.previous_monotonic]
    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: clock[0])
    original = reports()
    recorder.publication(original)
    original[0]["ran"] = False
    clock[0] += 101
    recorder.publication(reports(at=87))
    recorder.event({"kind": "storage"})
    assert recorder.status()["publication_backlog"]["oldest_age_seconds"] == 101
    first = collect(recorder)
    second = collect(recorder)
    assert "recording_gap" in first["flags"]
    assert len(first["events"]) == 7
    assert first["events"][-1]["kind"] == "storage"
    assert first["events"][0]["ran"] is True
    assert len(second["events"]) == 6
    assert {e["at"] for e in second["events"]} == {87}
    assert recorder.pending_publication_events == recorder.total_dropped == 0
    assert not collect(recorder)["events"]


def test_overflow_drops_whole_oldest_group_with_exact_categories(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    for at in range(5):
        recorder.publication(reports(at, proofs=6))
    assert recorder.pending_publication_events == 28
    assert recorder.loss_counts()["event_capacity"] == 7
    assert recorder.lost_event_categories == {"training": 1, "proof": 6, "storage": 0, "other": 0}
    saved = []
    for _ in range(4):
        recorder.event({"kind": "storage"})
        record = collect(recorder)
        assert len(record["events"]) == 8
        saved.extend(e for e in record["events"] if "publication" in e)
    assert [e["at"] for e in saved if e["kind"] == "training"] == [1, 2, 3, 4]
    assert len({(e["publication"][0], e["publication"][1]) for e in saved}) == 28
    assert all(e["publication"][2] == 7 for e in saved)


def test_invalid_report_does_not_erase_valid_siblings_or_claim_complete_group(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    data = reports()
    data[2]["bad"] = float("nan")
    data[4]["oversize"] = "x" * 3000
    data[3] = None
    recorder.publication(data)
    emitted = collect(recorder)["events"]
    assert [e["publication"][1] for e in emitted] == [0, 1, 5]
    assert all(e["publication"][2] == 6 for e in emitted)
    assert recorder.loss_counts()["event_input"] == 3
    assert recorder.lost_event_categories["proof"] == 3


@pytest.mark.parametrize("enabled", [False, True])
def test_disabled_and_oversized_group_are_bounded(tmp_path, enabled):
    recorder = DiagnosticsRecorder(tmp_path, enabled=enabled)
    recorder.publication(reports(proofs=9))
    assert recorder.pending_publication_events == (7 if enabled else 0)
    assert recorder.loss_counts()["event_capacity"] == (3 if enabled else 0)
    assert not recorder.queue


def test_recorded_time_and_original_time_survive_paging_and_retry(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.publication(reports(at=100))
    record = collect(recorder)
    assert len(record["events"]) == 6
    store = DiagnosticsStore(tmp_path)
    try:
        assert store.append(record)
        assert store.append(record)  # Same interval retry cannot duplicate its reports.
    finally:
        store.close()
    rows = read_events(tmp_path, before=record["end"] + 1, limit=100)
    assert len(rows) == 6
    assert {r["record"]["at"] for r in rows} == {100}
    assert {r["record"]["collected_at"] for r in rows} == {record["end"]}
    assert {r["cursor"][0] for r in rows} == {record["end"]}


def test_group_pressure_never_calls_writer_and_error_gets_remaining_slot(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.writer = SimpleNamespace(rejected=0)
    for _ in range(12):
        recorder.publication(reports(proofs=6))
    assert recorder.pending_publication_events == 28
    assert len(recorder.queue) == 0
    recorder.event({"kind": "storage"})
    recorder.event({"kind": "training_error"})
    assert collect(recorder)["events"][-1]["kind"] == "training_error"
    assert list(recorder.events) == [{"kind": "storage"}]


def test_interval_encoding_failure_is_not_reported_as_saved(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.publication(reports())
    recorder.collect(pipeline={}, context={"bad": float("nan")}, gauges={}, skills=[])
    assert not recorder.queue
    assert recorder.loss_counts()["interval_input"] == 1
    assert recorder.pending_publication_events == 0
    assert "recording_gap" in collect(recorder)["flags"]


def test_dense_family_reports_still_fit_writer_limits(tmp_path):
    import random
    from datetime import UTC, datetime

    from signal_arcade.diagnostics import PROOF_METRICS, artifact_summary
    from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
    from test_fitted_coverage import valid_metrics

    rng = random.Random(52)  # noqa: S311 -- reproducible compression boundary
    recorder = DiagnosticsRecorder(tmp_path)
    for family in ("linear", "xgboost"):
        artifact = SimpleNamespace(
            version=family,
            skill=SimpleNamespace(value="entry"),
            model_family=SimpleNamespace(value=family),
            qualified=False,
            created_at=datetime.now(UTC),
            sample_count=430,
            training_count=280,
            validation_count=140,
            metrics={**{key: rng.random() for key in PROOF_METRICS[:21]}, **valid_metrics()},
        )
        recorder.publication(
            [{"kind": "proof", "at": 1789778122.9295325, **artifact_summary(artifact)}]
        )
    record = collect(recorder)
    assert len(record["events"]) == 2
    for event in record["events"]:
        encode(event, max_payload=MAX_EVENT_PAYLOAD)
