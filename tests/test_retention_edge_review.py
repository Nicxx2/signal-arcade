"""Cross-boundary checks for publication retention and observational RPC sampling."""

import copy
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.collection_diagnostics import CollectionDiagnostics
from signal_arcade.intelligence.learning import LearningEngine
from test_v1104_refresh import scheduler_fixture


@pytest.mark.parametrize("lane", ["discovery", "policy"])
@pytest.mark.parametrize("reason", ["missing_state", "excluded_identity", "fresh_cache"])
@pytest.mark.parametrize("clock", ["naive", "far_future"])
def test_optional_measurement_cannot_fail_selection_on_an_ineligible_clock(lane, reason, clock):
    learner, states, now = scheduler_fixture()
    for state in states.values():
        state.last_reserve_at -= timedelta(minutes=5)
    mint = f"{lane}-0"
    item = learner.observations[mint] if lane == "discovery" else learner.evidence_episodes[mint]
    at = now.replace(tzinfo=None) if clock == "naive" else datetime.max.replace(tzinfo=UTC)
    setattr(item, "created_at" if lane == "discovery" else "entry_at", at)
    excluded = set()
    if reason == "missing_state":
        del states[mint]
    elif reason == "excluded_identity":
        excluded.add(mint)
    else:
        states[mint].last_reserve_at = now
    control = copy.deepcopy(learner)
    original = copy.deepcopy((learner.observations, learner.evidence_episodes, states))
    expected = LearningEngine.due_checkpoint_mints(
        control, states, now, limit=5, fresh=False, excluded_mints=excluded
    )
    tracker = CollectionDiagnostics()
    selected = LearningEngine.due_checkpoint_mints(
        learner,
        states,
        now,
        limit=5,
        fresh=False,
        excluded_mints=excluded,
        diagnostics=tracker,
        measure_selection=True,
    )
    assert selected == expected
    assert learner._checkpoint_served == control._checkpoint_served
    assert learner._checkpoint_turn == control._checkpoint_turn
    assert (learner.observations, learner.evidence_episodes, states) == original
    event = next(event for event in tracker.selection_events() if event["lane"] == lane)
    assert event["clock_unclassified"] == int(clock == "naive")
    assert mint not in selected


@pytest.mark.parametrize("horizon", [60, 300, 600, 900, 1200])
@pytest.mark.parametrize("offset", [-0.000001, 0, 90, 90.000001])
def test_excluded_classification_preserves_every_horizon_boundary(horizon, offset):
    learner, states, now = scheduler_fixture()
    learner.observations = {
        mint: learner.observations[mint] for mint in (f"discovery-{index}" for index in range(3))
    }
    learner.evidence_episodes.clear()
    for item in learner.observations.values():
        item.created_at = now - timedelta(seconds=horizon + offset)
        item.checkpoints = {str(h): object() for h in (60, 300, 600, 900, 1200) if h != horizon}
    del states["discovery-1"]
    tracker = CollectionDiagnostics()
    assert not LearningEngine.due_checkpoint_mints(
        learner,
        states,
        now,
        limit=5,
        fresh=False,
        excluded_mints={"discovery-0"},
        diagnostics=tracker,
        measure_selection=True,
    )
    event = tracker.selection_events()[0]
    for index, measured_horizon in enumerate(event["horizons"]):
        expected = [0] * 5
        if measured_horizon == horizon and offset >= 0:
            expected = [0, 0, 0, 0, 3] if offset > 90 else [0, 1, 1, 1, 0]
        assert event["counts"][index] == expected
    assert event["clock_unclassified"] == 0


def test_closed_work_does_not_become_an_unclassified_clock():
    learner, states, now = scheduler_fixture()
    item = learner.observations["discovery-0"]
    item.created_at = now.replace(tzinfo=None)
    item.checkpoints = {str(h): object() for h in (60, 300, 600, 900, 1200)}
    del states[item.mint]
    tracker = CollectionDiagnostics()
    LearningEngine.due_checkpoint_mints(
        learner,
        states,
        now,
        limit=5,
        fresh=False,
        diagnostics=tracker,
        measure_selection=True,
    )
    assert all(event["clock_unclassified"] == 0 for event in tracker.selection_events())


@pytest.mark.parametrize("seed", [7, 81, 309])
def test_mixed_publication_sizes_conserve_reports_through_repeated_overflow(tmp_path, seed):
    import random

    from signal_arcade.diagnostics import DiagnosticsRecorder
    from test_publication_backlog import collect, reports

    rng = random.Random(seed)  # noqa: S311 -- repeatable workload
    recorder = DiagnosticsRecorder(tmp_path)
    admitted = emitted = 0
    seen = set()

    def drain():
        nonlocal emitted
        record = collect(recorder)
        assert len(record["events"]) <= 8
        for event in record["events"]:
            key = tuple(event["publication"][:2])
            assert key not in seen
            seen.add(key)
            emitted += 1
        recorder.queue.clear()  # Immediate isolated handoff, not a storage/durability claim.

    for at in range(100):
        batch = reports(at=at, proofs=rng.randrange(7))
        recorder.publication(batch)
        admitted += len(batch)
        if rng.randrange(4) == 0:
            drain()
        assert len(recorder.publications) <= 4 and recorder.pending_publication_events <= 28
        assert admitted == (
            emitted + recorder.pending_publication_events + recorder.loss_counts()["event_capacity"]
        )
    while recorder.publications:
        drain()
    assert admitted == emitted + sum(recorder.lost_event_categories.values())


def test_interval_overflow_is_counted_in_intervals_without_inventing_event_counts(tmp_path):
    from signal_arcade.diagnostics import DiagnosticsRecorder
    from signal_arcade.diagnostics_store import DiagnosticsStore, read_events, read_page
    from test_publication_backlog import collect, reports

    recorder = DiagnosticsRecorder(tmp_path)
    import json

    for at in range(5):
        recorder.publication(reports(at=at, proofs=6))
        collect(recorder)
    assert recorder.loss_counts()["interval_queue"] == 1
    assert sum(recorder.lost_event_categories.values()) == 0
    queued = [json.loads(raw) for raw in recorder.queue]
    assert [record["seq"] for record in queued] == [1, 2, 3, 4]
    store = DiagnosticsStore(tmp_path)
    try:
        for record in queued:
            assert store.append(record)
    finally:
        store.close()
    events = read_events(tmp_path, before=queued[-1]["end"] + 1, limit=100)
    assert len(events) == 28 and {event["record"]["at"] for event in events} == {1, 2, 3, 4}
    assert (
        "recording_gap"
        in read_page(tmp_path, tier=0, before=queued[-1]["end"] + 1)[0]["record"]["flags"]
    )


def test_writer_omission_keeps_original_publication_indices(tmp_path):
    import random
    import string

    from signal_arcade.diagnostics import DiagnosticsRecorder
    from signal_arcade.diagnostics_store import DiagnosticsStore, read_events, read_page
    from test_publication_backlog import collect, reports

    recorder = DiagnosticsRecorder(tmp_path)
    batch = reports(proofs=3)
    rng = random.Random(72)  # noqa: S311 -- incompressible synthetic data
    batch[2]["detail"] = "".join(rng.choices(string.ascii_letters + string.digits, k=1500))
    recorder.publication(batch)
    record = collect(recorder)
    assert recorder.total_dropped == 0  # Valid input; the writer's compression limit is separate.
    store = DiagnosticsStore(tmp_path)
    try:
        assert store.append(record)
    finally:
        store.close()
    events = read_events(tmp_path, before=record["end"] + 1)
    assert [event["record"]["publication"][1] for event in events] == [0, 1, 3]
    assert all(event["record"]["publication"][2] == 4 for event in events)
    saved = read_page(tmp_path, tier=0, before=record["end"] + 1)[0]["record"]
    assert saved["omitted_events"] == 1 and "event_omitted" in saved["flags"]
