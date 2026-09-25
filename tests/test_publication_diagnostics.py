"""Publication reports share the bounded diagnostic cadence, never market authority."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import json
import time
from threading import Event
from types import SimpleNamespace

import pytest
from signal_arcade.models import EventKind, MarketEvent
from test_probe_retention import engine  # noqa: F401
from test_publication_pressure import queued_job


@pytest.fixture
def clock(engine, monkeypatch):  # noqa: F811
    import signal_arcade.diagnostics as diagnostics
    import signal_arcade.intelligence.learning as learning
    import signal_arcade.orchestrator as orchestration

    origin = time.monotonic()
    now = [origin]
    clock_api = SimpleNamespace(
        monotonic=lambda: now[0],
        time=lambda: 1_800_000_000 + now[0] - origin,
        process_time=time.process_time,
    )
    monkeypatch.setattr(diagnostics, "time", clock_api)
    monkeypatch.setattr(orchestration, "time", clock_api)
    monkeypatch.setattr(learning, "time", clock_api)
    engine.diagnostics.previous_monotonic = origin
    engine.diagnostics.previous_at = clock_api.time()
    engine.diagnostics.next_collection_monotonic = origin + 60
    engine.diagnostics.writer = SimpleNamespace(
        status={"state": "recording"},
        rejected=0,
        thread=SimpleNamespace(is_alive=lambda: True),
        allowed=Event(),
        offer=lambda raw: True,
        wait_status=lambda: {
            "reason": None,
            "reason_age_seconds": 0,
            "episodes_since_boot": {},
            "seconds_since_boot": {},
        },
    )
    return now


def publication(engine, clock, monkeypatch, *, artifacts=6):
    job = queued_job(engine)
    job.started_monotonic = clock[0]
    job.workspace._training_output.artifacts = [
        (
            SimpleNamespace(
                version=f"{clock[0]}-{index}",
                skill=SimpleNamespace(value="entry"),
                model_family=SimpleNamespace(value="linear"),
                qualified=False,
                created_at=None,
                sample_count=10,
                training_count=6,
                validation_count=4,
                metrics={},
            ),
            None,
            False,
        )
        for index in range(artifacts)
    ]
    monkeypatch.setattr(engine.learning, "finish_training_job", lambda *args, **kwargs: True)
    assert asyncio.run(engine._publish_training_job(engine.learning, job, None))
    return job


@pytest.mark.parametrize("first,second,end", [(16.81, 57.66, 68.40), (29.82, 68.62, 72.97)])
def test_observed_publications_keep_every_report_without_duplicate_counts(
    engine,
    clock,
    monkeypatch,
    first,
    second,
    end,  # noqa: F811
):
    origin = clock[0]
    engine._record_pipeline_recent("processed", lag_seconds=3, critical=True)
    clock[0] = origin + first
    publication(engine, clock, monkeypatch)
    assert engine.diagnostics.sequence == 0
    clock[0] = origin + second
    publication(engine, clock, monkeypatch)
    assert engine.diagnostics.sequence == 1
    first_record = json.loads(engine.diagnostics.queue[0])
    assert [event["kind"] for event in first_record["events"]] == [
        "training",
        *(["proof"] * 6),
        "retention_sample",
    ]
    assert [event["publication"][1] for event in first_record["events"][:7]] == list(range(7))
    assert first_record["pipeline"]["processed"] == 1
    assert engine.diagnostics.pending_publication_events == 7
    assert engine.diagnostics.total_dropped == 0
    engine._record_pipeline_recent("processed", lag_seconds=0.1)
    clock[0] = origin + end
    assert not engine.diagnostics.collection_due()
    clock[0] = engine.diagnostics.next_collection_monotonic
    engine._collect_diagnostics()
    last = json.loads(engine.diagnostics.queue[-1])
    assert last["pipeline"]["processed"] == 1
    assert last["pipeline"]["critical_count"] == 0
    assert last["pipeline"]["lag_max"] == 0.1
    assert len(last["events"]) == 7


@pytest.mark.parametrize(
    "age,collects",
    [
        (54.999999, False),
        (55, True),
        (59.999999, True),
        (60, True),
        (60.000001, True),
        (90, True),
        (90.000001, False),
    ],
)
def test_early_window_edges(engine, clock, monkeypatch, age, collects):  # noqa: F811
    origin = clock[0]
    publication(engine, clock, monkeypatch)
    clock[0] = origin + age
    publication(engine, clock, monkeypatch)
    assert engine.diagnostics.sequence == int(collects)
    assert engine.diagnostics.total_dropped == 0


@pytest.mark.parametrize(
    "reason",
    [
        "disabled",
        "writer_missing",
        "writer_dead",
        "writer_paused",
        "queue_full",
        "candidate_pressure",
        "pending_sell",
    ],
)
def test_reporting_yields_without_blocking_publication(engine, clock, monkeypatch, reason):  # noqa: F811
    publication(engine, clock, monkeypatch)
    clock[0] += 57
    recorder = engine.diagnostics
    if reason == "disabled":
        recorder.enabled = False
    elif reason == "writer_missing":
        recorder.writer = None
    elif reason == "writer_dead":
        recorder.writer.thread.is_alive = lambda: False
    elif reason == "writer_paused":
        recorder.writer.status["state"] = "paused_storage"
    elif reason == "queue_full":
        recorder.queue.extend([b"{}"] * 4)
    elif reason == "candidate_pressure":
        for index in range(101):
            engine.event_queue.put_nowait(
                (2, index, MarketEvent(event_id=str(index), source="test", kind=EventKind.TRADE))
            )
    else:
        monkeypatch.setattr(engine, "_has_pending_sell", lambda: True)
    publication(engine, clock, monkeypatch)
    assert recorder.sequence == 0
    assert recorder.loss_counts()["interval_queue"] == 0
    assert recorder.total_dropped == 0


@pytest.mark.parametrize("artifacts", [0, 1, 6])
def test_only_protected_overflow_needs_early_collection(engine, clock, monkeypatch, artifacts):  # noqa: F811
    # Optional rows can yield to proof without consuming an extra interval.
    for _ in range(7):
        engine.diagnostics.event({"kind": "storage"})
    clock[0] += 57
    publication(engine, clock, monkeypatch, artifacts=artifacts)
    assert engine.diagnostics.sequence == 0
    assert engine.diagnostics.lost_event_categories["proof"] == 0


def test_one_unbuildable_proof_preserves_publication_and_other_summaries(
    engine, clock, monkeypatch
):
    import signal_arcade.orchestrator as orchestration

    original = orchestration.artifact_summary

    def summary(artifact):
        if artifact.version.endswith("-2"):
            raise ValueError("malformed summary input")
        return original(artifact)

    monkeypatch.setattr(orchestration, "artifact_summary", summary)
    publication(engine, clock, monkeypatch)
    events = engine.diagnostics.publications[0][1]
    assert [event["publication"][1] for event in events] == [0, 1, 2, 4, 5, 6]
    assert all(event["publication"][2] == 7 for event in events)
    assert engine.diagnostics.lost_event_categories["proof"] == 1
    assert events[0]["kind"] == "training" and events[0]["ran"]


def test_reporting_failure_cannot_fail_publication_or_spin(engine, clock, monkeypatch):  # noqa: F811
    publication(engine, clock, monkeypatch)
    clock[0] += 57

    def fail():
        raise ValueError("isolated reporting failure")

    monkeypatch.setattr(engine, "_collect_diagnostics", fail)
    publication(engine, clock, monkeypatch)
    assert engine.diagnostics.loss_counts()["collector_error"] == 1
    publication(engine, clock, monkeypatch)
    assert engine.diagnostics.loss_counts()["collector_error"] == 1
    assert not engine._event_lock.locked()


def test_early_collection_cannot_accelerate_long_run_cadence(engine, clock, monkeypatch):  # noqa: F811
    origin = clock[0]
    for index in range(120):
        engine.diagnostics.events.clear()
        engine.diagnostics.publications.clear()
        engine.diagnostics.queue.clear()  # Healthy isolated writer drains each interval.
        publication(engine, clock, monkeypatch)
        clock[0] = origin + (index + 1) * 60 - 5
        publication(engine, clock, monkeypatch)
        assert engine.diagnostics.sequence == index + 1
        assert engine.diagnostics.next_collection_monotonic == origin + (index + 2) * 60
    assert engine.diagnostics.total_dropped == 0


@pytest.mark.parametrize("artifacts", [0, 1, 6])
def test_publication_reserves_only_the_reports_it_can_emit(engine, clock, monkeypatch, artifacts):
    publication(engine, clock, monkeypatch)
    clock[0] += 57
    publication(engine, clock, monkeypatch, artifacts=artifacts)
    assert engine.diagnostics.sequence == int(artifacts > 0)
    assert engine.diagnostics.total_dropped == 0


@pytest.mark.parametrize("terminal", ["error", "stale"])
def test_terminal_job_never_waits_for_diagnostic_collection(engine, clock, monkeypatch, terminal):
    publication(engine, clock, monkeypatch)
    clock[0] += 57
    job = queued_job(engine)
    job.started_monotonic = clock[0]
    if terminal == "stale":
        job.runtime_context = ()
    monkeypatch.setattr(engine, "_collect_before_publication", lambda *_: pytest.fail("terminal"))
    monkeypatch.setattr(engine.learning, "finish_training_job", lambda *_args, **_kwargs: False)
    assert not asyncio.run(
        engine._publish_training_job(
            engine.learning, job, ValueError("failed fit") if terminal == "error" else None
        )
    )


def test_third_close_publication_stays_pending_without_more_intervals(engine, clock, monkeypatch):
    publication(engine, clock, monkeypatch)
    clock[0] += 57
    publication(engine, clock, monkeypatch)
    clock[0] += 1
    publication(engine, clock, monkeypatch)
    assert engine.diagnostics.sequence == 1
    assert len(engine.diagnostics.queue) == 1
    assert engine.diagnostics.pending_publication_events == 14
    assert engine.diagnostics.loss_counts()["event_capacity"] == 0
    assert engine.diagnostics.lost_event_categories["training"] == 0
    assert engine.diagnostics.lost_event_categories["proof"] == 0


def test_collection_before_real_publication_preserves_durable_fit(settings):
    from signal_arcade.orchestrator import Orchestrator
    from test_v1104_training_history import training_fixture

    learner, database, _ = training_fixture(settings)
    engine = Orchestrator(settings)
    original_database = engine.database
    engine.learning, engine.database = learner, database
    recorder = engine.diagnostics
    recorder.writer = SimpleNamespace(
        status={"state": "recording"},
        rejected=0,
        thread=SimpleNamespace(is_alive=lambda: True),
        wait_status=lambda: {
            "reason": None,
            "reason_age_seconds": 0,
            "episodes_since_boot": {},
            "seconds_since_boot": {},
        },
    )
    try:
        job = learner.prepare_next_training(engine._training_runtime_context())
        learner.fit_training_job(job)
        recorder.previous_monotonic = time.monotonic() - 57
        recorder.next_collection_monotonic = recorder.previous_monotonic + 60
        for _ in range(7):
            recorder.event({"kind": "proof"})
        published = learner.training_status()["published_models"]
        assert asyncio.run(engine._publish_training_job(learner, job, None))
        assert learner.training_status()["published_models"] == published + 1
        assert recorder.sequence == 1 and recorder.total_dropped == 0
        report = recorder.publications[0][1][0]
        assert report["kind"] == "training" and report["ran"]
        restored = type(learner)(database, settings)
        assert {a.version for a in restored.skill_artifacts.values()} == {
            a.version for a in learner.skill_artifacts.values()
        }
    finally:
        asyncio.run(engine.http.close())
        original_database.close()
        database.close()


@pytest.mark.parametrize("change", ["urgent", "context", "age", "shutdown"])
def test_collection_rechecks_publication_admission(engine, clock, monkeypatch, change):  # noqa: F811
    publication(engine, clock, monkeypatch)
    clock[0] += 57
    job = queued_job(engine)
    job.workspace._training_output.artifacts = [None] * 6
    job.started_monotonic = clock[0]
    original = engine._collect_diagnostics
    waits, finished = [], []

    def collect():
        original()
        if change == "urgent":
            engine.event_queue.put_nowait(
                (0, 1, MarketEvent(event_id="urgent", source="test", kind=EventKind.TRADE))
            )
        elif change == "context":
            engine.broker.season_id = "new-season"
        elif change == "age":
            job.started_monotonic -= 121
        else:
            engine.stop_event.set()

    def finish(*args, runtime_context, **kwargs):
        stale = engine.learning.training_job_stale(job, runtime_context)
        finished.append(stale)
        assert stale or engine._learning_publication_can_run()
        return False

    async def wait(_seconds):
        waits.append(True)
        engine.event_queue.get_nowait()
        engine.event_queue.task_done()

    monkeypatch.setattr(engine, "_collect_diagnostics", collect)
    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    monkeypatch.setattr(engine.learning, "finish_training_job", finish)
    assert not asyncio.run(engine._publish_training_job(engine.learning, job, None))
    assert finished == [change != "urgent"]
    assert bool(waits) == (change == "urgent")


@pytest.mark.parametrize("change", ["collected", "pressure", "idle_lag", "training", "storage"])
def test_regular_collector_rechecks_after_waiting(engine, clock, monkeypatch, change):  # noqa: F811
    clock[0] += 61

    async def stop(_seconds):
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", stop)

    async def exercise():
        await engine._event_lock.acquire()
        task = asyncio.create_task(engine._diagnostics_loop())
        await asyncio.sleep(0)
        if change == "collected":
            engine._collect_diagnostics_safely()
        elif change in {"pressure", "idle_lag"}:
            engine.last_processing_lag_seconds = 2
            if change == "pressure":
                engine._event_batches_in_flight = 1
        elif change == "training":
            engine.learning._training_active = (engine.risk_mode, None)
        else:
            engine._storage_maintenance_active = True
        engine._event_lock.release()
        await asyncio.wait_for(task, 1)

    asyncio.run(exercise())
    assert engine.diagnostics.sequence == int(change in {"collected", "idle_lag"})
    assert engine.diagnostics.total_dropped == 0
