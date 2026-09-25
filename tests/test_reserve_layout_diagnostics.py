"""Unknown protocol layouts stay rejected while their bounded shape remains auditable."""

import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest
from signal_arcade.diagnostics_store import (
    MAX_EVENT_PAYLOAD,
    DiagnosticsStore,
    decode,
    encode,
    read_events,
)
from signal_arcade.intelligence.reserve_health import ReserveValidationHealth
from signal_arcade.intelligence.reserve_refresh import ReserveRefreshRejected, _decoded
from signal_arcade.orchestrator import Orchestrator
from test_v1104_refresh import route_fixture

CAPTURE = json.loads(
    (Path(__file__).parent / "fixtures/pump_global_unreviewed_20260912.json").read_text()
)


def rejected_global():
    _, _, decoder, _ = route_fixture()
    raw = base64.b64decode(CAPTURE["data_base64"], validate=True)
    assert hashlib.sha256(raw).hexdigest() == CAPTURE["sha256"]
    raw += b"\x01"  # A future field after the now-reviewed holder-reward extension.
    with pytest.raises(ReserveRefreshRejected, match="unreviewed_account_extension") as caught:
        _decoded(decoder, {"raw": raw}, CAPTURE["program"], "Global")
    return caught.value


def test_future_global_suffix_stays_rejected_and_reports_exact_review_boundary():
    error = rejected_global()
    assert error.account_type == "Global"
    assert error.layout == {
        "account_bytes": 1088,
        "reviewed_bytes": 1087,
        "unreviewed_bytes": 1,
        "sample_bytes": 1088,
        "sample_sha256": hashlib.sha256(
            base64.b64decode(CAPTURE["data_base64"]) + b"\x01"
        ).hexdigest(),
    }


def test_unsupported_prefix_and_long_unknown_suffix_have_bounded_details():
    _, _, decoder, _ = route_fixture()
    for raw in (b"short", base64.b64decode(CAPTURE["data_base64"]) + b"x" * 50_000):
        with pytest.raises(ReserveRefreshRejected) as caught:
            _decoded(decoder, {"raw": raw}, CAPTURE["program"], "Global")
        detail = caught.value.layout
        assert detail["account_bytes"] == len(raw)
        assert detail["sample_bytes"] == min(4096, len(raw))
        assert detail["sample_sha256"] == hashlib.sha256(raw[:4096]).hexdigest()
        assert len(json.dumps(detail)) < 256


def test_layout_snapshots_are_detached_and_only_matching_success_clears_them():
    health = ReserveValidationHealth()
    error = rejected_global()
    expected = copy.deepcopy(error.layout)
    for source in ("learning", "watchdog"):
        with health.batch(source) as batch:
            batch.rejected("pump_curve", error)
            batch.accepted("pump_swap")
    error.layout.clear()
    first = health.status(learning=True, watchdog=True)
    assert first["components"][0]["layout"] == expected
    first["components"][0]["layout"].clear()
    assert health.status(learning=True, watchdog=True)["components"][0]["layout"] == expected
    with health.batch("watchdog") as batch:
        batch.accepted("pump_curve")
    current = health.status(learning=True, watchdog=True)
    assert current["components"][0]["layout"] == expected
    assert current["components"][2]["layout"] is None


def test_layout_export_waits_behind_proof_and_collection_then_survives_storage(settings, tmp_path):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    engine.learning.collection_diagnostics.record("discovery", 300, "expired")
    try:
        with engine._reserve_validation.batch("learning") as batch:
            batch.rejected("pump_curve", rejected_global())
        for index in range(6):
            engine.diagnostics.event({"kind": "proof", "test_sequence": index})
        engine._record_collection_diagnostics()
        assert [e["kind"] for e in engine.diagnostics.events] == ["proof"] * 6 + [
            "collection",
            "collection",
        ]
        assert engine.diagnostics.dropped == 0
        engine.diagnostics._take_events(0)
        # Collection cadence must not strand the deferred layout sample for five minutes.
        engine._record_collection_diagnostics()
        assert [e["kind"] for e in engine.diagnostics.events] == ["reserve_layout"]
        event = copy.deepcopy(engine.diagnostics.events[0])
        assert event["layouts"][0]["account_bytes"] == 1088
        assert event["layouts"][1:] == [None, None, None]
        engine._collect_diagnostics()
        store = DiagnosticsStore(tmp_path / "layout-history")
        try:
            assert store.append(json.loads(engine.diagnostics.queue[-1]))
            rows = read_events(tmp_path / "layout-history", before=2e9)
            assert any(row["record"] == event for row in rows)
        finally:
            store.close()
        engine._record_collection_diagnostics()
        assert not engine.diagnostics.events
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_four_distinct_layout_samples_fit_event_budget_and_cadence(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    tick = [1000.0]
    monkeypatch.setattr("signal_arcade.orchestrator.time.monotonic", lambda: tick[0])
    try:
        for index, (source, venue) in enumerate(
            (s, v) for s in ("learning", "watchdog") for v in ("pump_curve", "pump_swap")
        ):
            error = rejected_global()
            error.layout["sample_sha256"] = hashlib.sha256(str(index).encode()).hexdigest()
            error.layout["account_bytes"] = 10_000_000 + index
            error.layout["sample_bytes"] = 4096
            with engine._reserve_validation.batch(source) as batch:
                batch.rejected(venue, error)
        engine._record_reserve_layout_diagnostics()
        event = engine.diagnostics._take_events(0)[-1]
        assert len(event["layouts"]) == 4
        assert decode(encode(event, max_payload=MAX_EVENT_PAYLOAD)) == event
        tick[0] += 299.999
        engine._record_reserve_layout_diagnostics()
        assert not engine.diagnostics.events
        tick[0] += 0.0011
        engine._record_reserve_layout_diagnostics()
        assert len(engine.diagnostics.events) == 1
        engine.diagnostics._take_events(0)
        engine.diagnostics.enabled = False
        tick[0] += 300
        engine._record_reserve_layout_diagnostics()
        assert not engine.diagnostics.events
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
