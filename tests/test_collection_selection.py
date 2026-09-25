"""Selection telemetry describes admitted work without changing its choices or clocks."""

import copy
import json
from datetime import timedelta

import pytest
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
from signal_arcade.intelligence.collection_diagnostics import CollectionDiagnostics
from signal_arcade.intelligence.learning import LearningEngine
from test_v1104_refresh import scheduler_fixture


@pytest.mark.parametrize("fresh", [False, True])
@pytest.mark.parametrize("limit", [0, 1, 5, 20])
def test_measurement_is_observational_across_rotation_and_channels(fresh, limit):
    learner, states, now = scheduler_fixture()
    if not fresh:
        for state in states.values():
            state.last_reserve_at -= timedelta(minutes=5)
    control = copy.deepcopy(learner)
    original = copy.deepcopy((learner.observations, learner.evidence_episodes, states))
    tracker = CollectionDiagnostics()
    for offset in (0, 11, 22):
        kwargs = dict(limit=limit, fresh=fresh, excluded_mints={"discovery-0"})
        selected = LearningEngine.due_checkpoint_mints(
            learner,
            states,
            now + timedelta(seconds=offset),
            diagnostics=tracker,
            measure_selection=True,
            **kwargs,
        )
        expected = LearningEngine.due_checkpoint_mints(
            control, states, now + timedelta(seconds=offset), **kwargs
        )
        assert selected == expected
        assert learner._checkpoint_served == control._checkpoint_served
        assert learner._checkpoint_turn == control._checkpoint_turn
    assert (learner.observations, learner.evidence_episodes, states) == original
    events = tracker.selection_events()
    assert len(events) == (0 if fresh else 2)
    if events:
        assert all(e["pass"] == 1 for e in events)
        assert all(e["sampled_at"] == now.timestamp() for e in events)


def test_eligibility_categories_are_disjoint_and_exclude_future_or_closed_work():
    learner, states, now = scheduler_fixture()
    for state in states.values():
        state.last_reserve_at -= timedelta(minutes=5)
    states["discovery-0"].last_reserve_at = now
    del states["discovery-2"]
    learner.observations["discovery-3"].created_at = now - timedelta(seconds=151)
    learner.observations["discovery-4"].checkpoints["60"] = object()
    learner.observations["discovery-5"].created_at = now - timedelta(seconds=59.999999)
    tracker = CollectionDiagnostics()
    LearningEngine.due_checkpoint_mints(
        learner,
        states,
        now,
        limit=5,
        fresh=False,
        excluded_mints={"discovery-1"},
        diagnostics=tracker,
        measure_selection=True,
    )
    event = tracker.selection_events()[0]
    assert event["counts"][0] == [18, 1, 1, 1, 1]
    assert event["counts"][1:] == [[0] * 5] * 4
    assert event["budget"] == [5, 42, 5]
    assert event["routes"] == [0, 0, 18, 1]
    assert event["selected_bands"] == [0, 0, 1]
    assert event["unselected_bands"] == [0, 0, 17]
    assert event["guard_context"] == "not_reported"
    assert event["sampled_at"] == now.timestamp()


@pytest.mark.parametrize(
    "remaining,bucket", [(0, 0), (5, 0), (5.000001, 1), (15, 1), (15.000001, 2)]
)
def test_deadline_buckets_and_shared_mint_use_original_lane_clocks(remaining, bucket):
    learner, states, now = scheduler_fixture()
    for state in states.values():
        state.last_reserve_at -= timedelta(minutes=5)
    observation = learner.observations.pop("discovery-0")
    observation.mint = "policy-0"
    observation.created_at = now - timedelta(seconds=150 - remaining)
    learner.observations[observation.mint] = observation
    tracker = CollectionDiagnostics()
    selected = LearningEngine.due_checkpoint_mints(
        learner,
        states,
        now,
        limit=48,
        fresh=False,
        diagnostics=tracker,
        measure_selection=True,
    )
    discovery, policy = tracker.selection_events()
    assert len(selected) == len(set(selected)) == 47
    assert discovery["budget"] == policy["budget"] == [48, 47, 47]
    assert discovery["routes"][bucket] == (24 if bucket == 2 else 1)
    assert discovery["routes"][3] == policy["routes"][3] == 24
    assert policy["routes"] == [0, 0, 24, 24]
    assert discovery["selected_bands"] == discovery["routes"][:3]
    assert discovery["unselected_bands"] == policy["unselected_bands"] == [0, 0, 0]


def test_sample_is_opt_in():
    learner, states, now = scheduler_fixture()
    tracker = CollectionDiagnostics()
    LearningEngine.due_checkpoint_mints(
        learner,
        states,
        now,
        limit=5,
        fresh=False,
        diagnostics=tracker,
    )
    assert not tracker.selection_events()


def test_measurement_cooldown_uses_monotonic_clock_and_resets_with_scope(monkeypatch):
    from types import SimpleNamespace

    import signal_arcade.intelligence.collection_diagnostics as module

    clock = [100.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 0))
    learner, states, now = scheduler_fixture()
    tracker = CollectionDiagnostics()
    for offset, expected in [(0, 1), (59.999999, 1), (60, 2), (60.000001, 2), (120, 3)]:
        clock[0] = 100 + offset
        LearningEngine.due_checkpoint_mints(
            learner,
            states,
            now - timedelta(days=offset),
            limit=5,
            fresh=False,
            diagnostics=tracker,
            measure_selection=True,
        )
        assert tracker.selection_events()[0]["pass"] == expected
    replacement = CollectionDiagnostics()
    assert replacement.scope != tracker.scope and replacement.selection_sample_due()


def test_guarded_and_disabled_passes_do_not_consume_a_measurement(settings, monkeypatch):
    import asyncio

    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    blocked = ["processing_lag"]
    monkeypatch.setattr(engine, "_learning_reserve_blocked_reason", lambda: blocked[0])
    tracker = engine.learning.collection_diagnostics
    try:
        assert asyncio.run(engine._learning_reserve_tick()) == "processing_lag"
        assert not tracker.selection_events() and tracker.selection_sample_due()
        blocked[0] = None
        engine.diagnostics.enabled = False
        asyncio.run(engine._learning_reserve_tick())
        assert not tracker.selection_events() and tracker.selection_sample_due()
        engine.diagnostics.enabled = True
        asyncio.run(engine._learning_reserve_tick())
        assert tracker.selection_events()[0]["pass"] == 1
        assert tracker.selection_events()[0]["guard_context"] == "preselection_passed"
        asyncio.run(engine._learning_reserve_tick())
        assert tracker.selection_events()[0]["pass"] == 1
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_selection_payloads_fit_maximum_counters_and_have_no_route_identity():
    from datetime import UTC, datetime

    tracker = CollectionDiagnostics()
    tracker._selection_passes = 2**53 - 1
    tracker.selection_sample(
        datetime.now(UTC),
        {
            lane: [[2**53 - i - j - 1 for i in range(5)] for j in range(5)]
            for lane in ("discovery", "policy")
        },
        {lane: [2**53 - 1] * 4 for lane in ("discovery", "policy")},
        [20, 2**53 - 1, 20],
        clock_unclassified={lane: 2**53 - 1 for lane in ("discovery", "policy")},
    )
    for event in tracker.selection_events():
        assert event["pass"] == 2**53 - 1
        assert len(json.dumps(event).encode()) < 2048
        encode(event, max_payload=MAX_EVENT_PAYLOAD)
        assert "mint" not in event and "identities" not in event


def test_optional_selection_yields_to_loss_detail_and_retries_without_displacing_proof(settings):
    import asyncio
    from datetime import UTC, datetime

    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    tracker = engine.learning.collection_diagnostics
    tracker.selection_sample(
        datetime.now(UTC),
        {lane: [[0] * 5 for _ in range(5)] for lane in ("discovery", "policy")},
        {lane: [0] * 4 for lane in ("discovery", "policy")},
        [5, 0, 0],
    )
    try:
        for index in range(7):
            engine.diagnostics.event({"kind": "proof", "id": index})
        engine.diagnostics.recording_failed(collection=False)
        engine._record_collection_detail_diagnostics()
        assert [event["kind"] for event in engine.diagnostics.events] == ["proof"] * 7 + [
            "diagnostic_loss"
        ]
        engine.diagnostics._take_events(0)
        engine._record_collection_detail_diagnostics()
        assert [event["kind"] for event in engine.diagnostics.events] == [
            "collection_selection",
            "collection_selection",
            "retention_sample",
        ]
        assert engine.diagnostics.total_dropped == 1  # Only the explicitly injected failure.
        engine.diagnostics._take_events(0)
        engine._record_collection_detail_diagnostics()
        assert not engine.diagnostics.events  # Successful emissions keep their normal cadence.
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
