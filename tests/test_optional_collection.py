"""Collection cadence follows actual selection, with finite fair optional admission."""

import json
import random

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_optional import optional_key, runtime_work_parts
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, decode, encode
from test_diagnostics import interval
from test_publication_backlog import reports


def sample(kind="collection", lane="discovery", scope="scope", at=1):
    value = {"kind": kind, "scope": scope, "at": at}
    if lane:
        value["lane"] = lane
    if kind.startswith("collection"):
        value["horizons"] = [60, 300, 600, 900, 1200]
    return value


def test_accepted_then_evicted_retries_without_false_cooldown(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    discovery, policy = sample(), sample(lane="policy")
    recorder.optional_events([discovery, policy])
    for _ in range(7):
        recorder.event({"kind": "storage"})
    assert discovery not in recorder.events and policy in recorder.events
    assert recorder.total_dropped == 1
    recorder._take_events(10)
    recorder.optional_events([discovery, policy])
    assert list(recorder.events) == [discovery]
    assert recorder.total_dropped == 1


def test_slow_sample_survives_eviction_and_exact_collection_releases_it(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    evidence = recorder.runtime_evidence
    evidence.observe_slow("storage", started=1, finished=8, at=100, phases={}, outcome="error")
    old = evidence.slow_event("storage", recorder.boot)
    recorder.optional_events([old])
    for _ in range(8):
        recorder.event({"kind": "storage"})
    assert evidence.slow_event("storage", recorder.boot) == old
    recorder._take_events(101)
    recorder.optional_events([old])
    evidence.observe_slow("storage", started=10, finished=19, at=102, phases={}, outcome="complete")
    recorder._take_events(103)
    assert evidence.slow["storage"]["at"] == 102  # Old collection cannot erase new sample.


def test_cumulative_replacement_keeps_latest_scope_time_and_is_counted(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    first = {**sample(), "counts": [1]}
    latest = {**sample(at=2), "counts": [3]}
    recorder.optional_events([first])
    recorder.optional_events([latest])
    latest["counts"][0] = 99
    assert list(recorder.events) == [{**sample(at=2), "counts": [3]}]
    assert recorder.optional_coalesced == 1 and recorder.total_dropped == 0
    recorder.optional_events([sample(scope="new", at=3)])
    assert recorder.events[0]["scope"] == "scope"
    recorder._take_events(4)
    recorder.optional_events([sample(scope="new", at=3)])
    assert recorder.events[0]["scope"] == "new"


def test_all_optional_streams_get_a_turn_under_repeated_complete_publications(
    tmp_path, monkeypatch
):
    recorder = DiagnosticsRecorder(tmp_path)
    clock = [1000.0]
    monkeypatch.setattr("signal_arcade.diagnostics.time.monotonic", lambda: clock[0])
    candidates = [
        sample(kind, lane)
        for kind in ("collection", "collection_expiry", "collection_selection")
        for lane in ("discovery", "policy")
    ]
    candidates += [
        sample(kind, "")
        for kind in (
            "reserve_layout",
            "runtime_work",
            "heartbeat_work",
            "collector_work",
            "retention_sample",
        )
    ]
    candidates += [sample("provider_health", lane) for lane in ("http", "ws")]
    candidates += [sample("collector_work", "writer")]
    candidates += [sample("runtime_work", lane) for lane in ("guards", "snapshot", "rpc")]
    seen = set()
    for _ in range(25):
        recorder.publication(reports(proofs=6))
        recorder.optional_events(candidates)
        selected = recorder._take_events(clock[0])
        assert len(selected) == 8 and sum("publication" in e for e in selected) == 7
        seen.add(optional_key(selected[-1]))
        assert len(recorder.events) <= 8
        clock[0] += 60
    assert seen == {optional_key(event) for event in candidates}
    assert recorder.total_dropped == 0


def test_cooldown_exact_boundary_and_new_scope_are_independent(tmp_path, monkeypatch):
    recorder = DiagnosticsRecorder(tmp_path)
    clock = [1000.0]
    monkeypatch.setattr("signal_arcade.diagnostics.time.monotonic", lambda: clock[0])
    recorder.optional_events([sample(), sample(lane="policy")])
    recorder._take_events(10)
    clock[0] += 299.999
    recorder.optional_events([sample()])
    assert not recorder.events
    recorder.optional_events([sample(lane="policy", scope="new")])
    assert len(recorder.events) == 1
    clock[0] = 1300
    recorder.optional_events([sample()])
    assert len(recorder.events) == 2


@pytest.mark.parametrize(
    "bad", [{"lane": []}, {"scope": "x" * 65}, {"horizons": [999]}, {"kind": "proof"}]
)
def test_invalid_optional_dimensions_do_not_grow_state_or_take_authority(tmp_path, bad):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.optional_events([{**sample(), **bad}])
    assert not recorder.events and not recorder._optional_collected
    assert recorder.total_dropped == 1


def test_collected_is_not_saved_when_interval_encoding_fails(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.optional_events([sample()])
    recorder.collect(
        pipeline=interval()["pipeline"], context={"bad": float("nan")}, gauges={}, skills=[]
    )
    assert not recorder.queue and recorder.loss_counts()["interval_input"] == 1
    recorder.collect(pipeline=interval()["pipeline"], context={}, gauges={}, skills=[])
    assert "recording_gap" in json.loads(recorder.queue[-1])["flags"]
    encode(sample(), max_payload=MAX_EVENT_PAYLOAD)


def test_repeated_scope_changes_do_not_grow_cadence_state(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    for index in range(200):
        recorder.optional_events([sample(scope=str(index))])
        assert len(recorder.events) == 1
        recorder._take_events(index)
    assert len(recorder._optional_collected) == 1
    recorder.enabled = False
    recorder.optional_events([sample(scope="disabled")])
    assert not recorder.events and recorder.total_dropped == 0


@pytest.mark.parametrize(
    "elapsed", ["slow", None, [], {}, True, -1, float("nan"), float("inf"), 1e12 + 1]
)
def test_invalid_slow_replacement_cannot_interrupt_proof_collection(tmp_path, elapsed):
    recorder = DiagnosticsRecorder(tmp_path)
    good = {**sample("slow_work", "market"), "elapsed": 2}
    recorder.optional_events([good])
    recorder.publication(reports(proofs=6))
    recorder.optional_events([{**good, "elapsed": elapsed}, sample(lane="policy")])
    assert list(recorder.events) == [good, sample(lane="policy")]
    assert recorder.optional_coalesced == 0
    assert recorder.loss_counts()["event_input"] == 1
    selected = recorder._take_events(10)
    assert len(selected) == 8 and sum("publication" in event for event in selected) == 7
    assert selected[-1] == good


def test_generic_malformed_slow_event_cannot_poison_optional_replacement(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    bad = {**sample("slow_work", "market"), "elapsed": "slow"}
    good = {**bad, "elapsed": 3}
    assert recorder.event(bad)  # Generic event submission validates JSON, not optional shape.
    recorder.optional_events([good])
    assert list(recorder.events) == [bad, good]
    recorder._take_events(10)
    assert len(recorder._optional_collected) == 1


@pytest.mark.parametrize("elapsed", [0, 0.0, 1e12])
def test_slow_elapsed_boundaries_remain_valid(tmp_path, elapsed):
    recorder = DiagnosticsRecorder(tmp_path)
    event = {**sample("slow_work", "market"), "elapsed": elapsed}
    recorder.optional_events([event])
    assert list(recorder.events) == [event] and recorder.total_dropped == 0


def test_runtime_split_transitions_preserve_frames_and_do_not_displace_proof(tmp_path, monkeypatch):
    recorder = DiagnosticsRecorder(tmp_path)
    clock = [1000.0]
    monkeypatch.setattr("signal_arcade.diagnostics.time.monotonic", lambda: clock[0])
    rng = random.Random(20260921)  # noqa: S311 - deterministic encoding boundary fixture
    names = [
        "snapshot_" + n
        for n in ("portfolio", "history", "tokens", "decisions", "learning", "advisory", "other")
    ] + [
        "rpc_" + n for n in ("selection_wait", "request", "result_wait", "storage_handoff", "apply")
    ]
    split_frames = []
    for index, large in enumerate((False, True, False)):
        event = {
            "kind": "runtime_work",
            "version": 1,
            "scope": recorder.boot,
            "at": clock[0],
            "seconds_since_boot": {
                name: [rng.randrange(2**52), rng.random() * 1e12, rng.random() * 1e5]
                for name in names
            }
            if large
            else {"rpc_request": [index + 1, 1.5, 1.0]},
            "ai_dispatch_since_boot": {"dispatch": 2**53 - 1, "not_due": 2**53 - 2},
            "discarded_batches_since_boot": {
                name: rng.randrange(2**53)
                for name in (
                    "disabled",
                    "demo",
                    "maintenance",
                    "market_boundary",
                    "pending_sell",
                    "queue_pressure",
                    "processing_lag",
                    "market_unhealthy",
                    "context_changed",
                )
            },
            "maintenance_guards_since_boot": {
                name: {"deferred": rng.randrange(2**53), "discarded": rng.randrange(2**53)}
                for name in ("upgrade", "storage", "unspecified")
            },
            "storage_handoff_since_boot": {
                name: rng.randrange(2**53)
                for name in ("waited", "idle_observed", "timed_out", "interrupted")
            },
        }
        original = json.dumps(event, sort_keys=True)
        parts = runtime_work_parts(event)
        split_frames.append(len(parts))
        recorder.optional_events(parts)
        saved = []
        for _ in parts:
            recorder.publication(reports(proofs=6))
            selected = recorder._take_events(clock[0])
            assert len(selected) == 8 and sum("publication" in e for e in selected) == 7
            saved.append(decode(encode(selected[-1], max_payload=MAX_EVENT_PAYLOAD)))
        assert json.dumps(event, sort_keys=True) == original
        assert all(e["scope"] == event["scope"] and e["at"] == event["at"] for e in saved)
        assert {k: v for e in saved for k, v in e["seconds_since_boot"].items()} == event[
            "seconds_since_boot"
        ]
        for key in (
            "ai_dispatch_since_boot",
            "discarded_batches_since_boot",
            "maintenance_guards_since_boot",
            "storage_handoff_since_boot",
        ):
            assert [e[key] for e in saved if key in e] == [event[key]]
        assert not recorder.events and recorder.total_dropped == 0
        clock[0] += 301
    assert split_frames == [1, 3, 1]
    assert len(recorder._optional_collected) == 4
