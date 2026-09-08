"""Urgent persistence remains bounded, causal and durable before processing."""

import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from signal_arcade.config import Settings
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.orchestrator import Orchestrator


@pytest.mark.parametrize("duplicates", [False, True])
@pytest.mark.parametrize("urgent_count", [1, 20, 70])
@pytest.mark.parametrize("batch_size", [10, 16, 32])
def test_urgent_arrivals_use_bounded_transactions_and_keep_fairness(
    tmp_path, monkeypatch, duplicates, urgent_count, batch_size
):
    engine = Orchestrator(
        Settings(
            data_dir=tmp_path,
            demo_mode=True,
            event_batch_size=batch_size,
            _env_file=None,
        )
    )
    engine.running = True
    engine.features.tokens["held"] = TokenState(mint="held")
    for index in range(batch_size):
        mint = f"candidate-{index}"
        engine.features.tokens[mint] = TokenState(mint=mint)
    monkeypatch.setattr(engine, "_critical_event", lambda event: event.mint == "held")
    writes, handled, inflight = [], [], []
    append = engine.database.append_events

    def persist(events):
        writes.append([event.event_id for event in events])
        return append(events)

    monkeypatch.setattr(engine.database, "append_events", persist)

    async def handle(event, *, sequence=None):
        if event.mint == "held":
            assert any(event.event_id in batch for batch in writes)
            assert any(
                row.event_id == event.event_id for row in engine.database.recent_events(200)
            )  # Committed before side effects.
        handled.append(event.event_id)
        inflight.append(len(engine.event_queue._dequeued_sequences))
        if event.event_id == "candidate-0":
            for index in range(urgent_count):
                urgent = MarketEvent(
                    event_id=f"urgent-{index}",
                    source="test",
                    kind=EventKind.TRADE,
                    mint="held",
                )
                await engine.enqueue_event(urgent)
                if duplicates:
                    await engine.enqueue_event(urgent)
        return True

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)

    async def exercise():
        for index in range(batch_size):
            await engine.enqueue_event(
                MarketEvent(
                    event_id=f"candidate-{index}",
                    source="test",
                    kind=EventKind.TRADE,
                    mint=f"candidate-{index}",
                )
            )
        worker = asyncio.create_task(engine._event_worker_loop())
        try:
            await asyncio.wait_for(engine.event_queue.join(), 10)
        finally:
            engine.stop_event.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            await engine.http.close()

    try:
        asyncio.run(exercise())
        first_urgent_count = min(urgent_count, batch_size // (2 if duplicates else 1))
        assert handled == [
            "candidate-0",
            *[f"urgent-{i}" for i in range(first_urgent_count)],
            *[f"candidate-{i}" for i in range(1, batch_size)],
            *[f"urgent-{i}" for i in range(first_urgent_count, urgent_count)],
        ]
        assert max(inflight) <= 2 * batch_size
        assert engine.events_processed == batch_size + urgent_count
        assert engine.events_persisted == urgent_count
        assert not engine.event_queue._pending_sequences
        assert engine._event_batches_in_flight == 0
        # No timing threshold: prove fewer transactions for an actual urgent burst.
        if urgent_count >= 20 and batch_size == 32:
            assert len(writes) <= 7
        assert all(len(batch) <= batch_size for batch in writes)
    finally:
        engine.database.close()


def test_newly_protected_prefetched_event_precedes_buffered_urgent_arrivals(tmp_path, monkeypatch):
    engine = Orchestrator(
        Settings(
            data_dir=tmp_path,
            demo_mode=True,
            event_batch_size=10,
            _env_file=None,
        )
    )
    engine.running = True
    for mint in ("first", "promoted", "last", "held"):
        engine.features.tokens[mint] = TokenState(mint=mint)
    protected = {"held"}
    monkeypatch.setattr(engine, "_critical_event", lambda event: event.mint in protected)
    handled = []

    async def handle(event, *, sequence=None):
        handled.append(event.event_id)
        if event.event_id == "first":
            for index in range(4):
                await engine.enqueue_event(
                    MarketEvent(
                        event_id=f"urgent-{index}",
                        source="test",
                        kind=EventKind.TRADE,
                        mint="held",
                    )
                )
        elif event.event_id == "urgent-1":
            protected.add("promoted")  # For example, an order was just created.
        elif event.event_id == "promoted":
            assert any(row.event_id == "promoted" for row in engine.database.recent_events(20))
        return True

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)

    async def exercise():
        for mint in ("first", "promoted", "last"):
            await engine.enqueue_event(
                MarketEvent(
                    event_id=mint,
                    source="test",
                    kind=EventKind.TRADE,
                    mint=mint,
                )
            )
        worker = asyncio.create_task(engine._event_worker_loop())
        try:
            await asyncio.wait_for(engine.event_queue.join(), 5)
        finally:
            engine.stop_event.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            await engine.http.close()

    try:
        asyncio.run(exercise())
        assert handled == [
            "first",
            "urgent-0",
            "urgent-1",
            "promoted",
            "urgent-2",
            "urgent-3",
            "last",
        ]
        assert engine.events_persisted == 5
        assert not engine.event_queue._pending_sequences
    finally:
        engine.database.close()


@pytest.mark.parametrize("interruption", ["rollback", "cancel"])
def test_interrupted_urgent_transaction_keeps_commit_and_season_boundaries(
    tmp_path, monkeypatch, interruption
):
    engine = Orchestrator(
        Settings(
            data_dir=tmp_path,
            demo_mode=True,
            event_batch_size=10,
            _env_file=None,
        )
    )
    engine.running = True
    for mint in ("first", "last", "held"):
        engine.features.tokens[mint] = TokenState(mint=mint)
    monkeypatch.setattr(engine, "_critical_event", lambda event: event.mint == "held")
    entered, release = Event(), Event()
    handled = []
    append = engine.database.append_events

    def persist(events):
        if any(event.event_id == "urgent-1" for event in events) and interruption == "cancel":
            entered.set()
            assert release.wait(5), "test did not release persistence"
        return append(events)

    monkeypatch.setattr(engine.database, "append_events", persist)
    if interruption == "rollback":
        engine.database._conn.execute(
            "CREATE TRIGGER fail_urgent BEFORE INSERT ON market_events "
            "WHEN NEW.event_id='urgent-2' BEGIN SELECT RAISE(ABORT,'injected failure'); END"
        )

    async def handle(event, *, sequence=None):
        handled.append(event.event_id)
        if event.event_id == "first":
            for index in range(3):
                await engine.enqueue_event(
                    MarketEvent(
                        event_id=f"urgent-{index}",
                        source="test",
                        kind=EventKind.TRADE,
                        mint="held",
                    )
                )
            engine.event_queue.begin_boundary(engine._event_sequence)
            await engine.enqueue_event(
                MarketEvent(
                    event_id="later-season",
                    source="test",
                    kind=EventKind.TRADE,
                    mint="held",
                )
            )
        return True

    async def stop_on_failure(_now):
        if engine._event_worker_incident_active:
            engine.stop_event.set()

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)
    monkeypatch.setattr(engine, "_update_queue_incident", stop_on_failure)

    async def exercise():
        for mint in ("first", "last"):
            await engine.enqueue_event(
                MarketEvent(
                    event_id=mint,
                    source="test",
                    kind=EventKind.TRADE,
                    mint=mint,
                )
            )
        worker = asyncio.create_task(engine._event_worker_loop())
        try:
            if interruption == "cancel":
                assert await asyncio.to_thread(entered.wait, 3)
                for _ in range(2):
                    worker.cancel()
                    await asyncio.sleep(0)
                assert not worker.done()
                assert not engine.event_queue.boundary_ready()
                assert engine._event_batches_in_flight == 1
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(worker, 3)
            else:
                await asyncio.wait_for(worker, 5)
            assert handled == ["first", "urgent-0"]
            assert engine._event_batches_in_flight == 0
            assert engine.event_queue.boundary_ready()
            assert engine.event_queue.qsize() == 1
            durable = {event.event_id for event in engine.database.recent_events(20)}
            assert durable == (
                {"urgent-0", "urgent-1", "urgent-2"} if interruption == "cancel" else {"urgent-0"}
            )
            if interruption == "rollback":
                assert "held" in engine._integrity_mint_gap_at
            engine.event_queue.end_boundary()
            assert engine.event_queue.get_nowait()[2].event_id == "later-season"
            engine.event_queue.task_done()
            await asyncio.wait_for(engine.event_queue.join(), 1)
        finally:
            release.set()
            engine.stop_event.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


@pytest.mark.parametrize(
    "change", ["late_arrival", "lost_protection", "stored_duplicate", "handler_failure"]
)
def test_buffered_urgent_evidence_rechecks_changes_while_persistence_is_in_flight(
    tmp_path, monkeypatch, change
):
    engine = Orchestrator(
        Settings(
            data_dir=tmp_path,
            demo_mode=True,
            event_batch_size=10,
            _env_file=None,
        )
    )
    engine.running = True
    for mint in ("first", "last", "held", "other", "due"):
        engine.features.tokens[mint] = TokenState(mint=mint)
    protected = {"held", "other"}
    monkeypatch.setattr(engine, "_critical_event", lambda event: event.mint in protected)
    monkeypatch.setattr(
        engine.learning,
        "pending_event_priority",
        lambda mint, _at: 0 if mint == "due" else None,
    )
    old = datetime.now(UTC) - timedelta(seconds=engine.settings.stale_market_seconds + 1)
    urgent = [
        MarketEvent(
            event_id=f"urgent-{i}",
            source="test",
            kind=EventKind.TRADE,
            mint=mint,
            received_at=old,
        )
        for i, mint in enumerate(("held", "held", "other", "due", "held"))
    ]
    if change == "stored_duplicate":
        assert engine.database.append_event(urgent[2])
    entered, release = Event(), Event()
    append = engine.database.append_events
    handled = []

    def persist(events):
        if any(event.event_id == "urgent-1" for event in events):
            entered.set()
            assert release.wait(5), "test did not release persistence"
        return append(events)

    monkeypatch.setattr(engine.database, "append_events", persist)

    async def handle(event, *, sequence=None):
        if event.event_id.startswith("urgent-"):
            assert any(row.event_id == event.event_id for row in engine.database.recent_events(20))
        if change == "handler_failure" and event.event_id == "urgent-2":
            raise RuntimeError("injected handler failure after committed batch")
        handled.append(event.event_id)
        if event.event_id == "first":
            for item in urgent:
                await engine.enqueue_event(item)
        return True

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)

    async def change_during_write():
        assert await asyncio.to_thread(entered.wait, 3)
        if change == "late_arrival":
            await engine.enqueue_event(urgent[0].model_copy(update={"event_id": "urgent-5"}))
            await engine.enqueue_event(urgent[1])
        elif change == "lost_protection":
            protected.remove("other")
        release.set()

    async def exercise():
        for mint in ("first", "last"):
            await engine.enqueue_event(
                MarketEvent(
                    event_id=mint,
                    source="test",
                    kind=EventKind.TRADE,
                    mint=mint,
                )
            )
        worker = asyncio.create_task(engine._event_worker_loop())
        controller = asyncio.create_task(change_during_write())
        try:
            await asyncio.wait_for(controller, 5)
            await asyncio.wait_for(engine.event_queue.join(), 5)
        finally:
            release.set()
            engine.stop_event.set()
            controller.cancel()
            worker.cancel()
            await asyncio.gather(worker, controller, return_exceptions=True)
            await engine.http.close()

    try:
        asyncio.run(exercise())
        expected = ["first", "urgent-0", "urgent-1", "urgent-2", "urgent-3", "urgent-4", "last"]
        if change == "late_arrival":
            expected.insert(-1, "urgent-5")
        elif change in {"lost_protection", "stored_duplicate"}:
            expected.remove("urgent-2")
        else:
            expected = expected[:3]
            assert engine._event_worker_incident_active
            assert {"other", "due", "held"} <= engine._integrity_mint_gap_at.keys()
        assert handled == expected
        assert engine.events_processed == len(expected)
        assert engine.expired_candidate_events == int(change == "lost_protection")
        assert not engine.event_queue._pending_sequences
        assert engine._event_batches_in_flight == 0
        if change == "lost_protection":
            assert "other" in engine._integrity_mint_gap_at
            assert "due" not in engine._integrity_mint_gap_at
    finally:
        engine.database.close()
