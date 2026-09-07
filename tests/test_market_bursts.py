from __future__ import annotations

import asyncio
import hashlib

import pytest
from signal_arcade.config import Settings
from signal_arcade.event_queue import SeasonEventQueue
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.providers.anchor import BASE58_ALPHABET, b58encode


def test_native_public_key_encoding_preserves_every_leading_zero_and_generic_width():
    def reference(data: bytes) -> str:
        zeros = len(data) - len(data.lstrip(b"\0"))
        number = int.from_bytes(data, "big")
        encoded = ""
        while number:
            number, remainder = divmod(number, 58)
            encoded = BASE58_ALPHABET[remainder] + encoded
        return "1" * zeros + (encoded or ("" if zeros else "1"))

    values = [b"", bytes(32), bytes([255]) * 32]
    for length in range(66):
        values.extend([bytes(length), bytes(range(length))])
    for index in range(256):
        digest = hashlib.sha256(str(index).encode()).digest()
        values.append(digest)
        zeros = index % 33
        values.append(bytes(zeros) + digest[zeros:])
    assert [b58encode(value) for value in values] == [reference(value) for value in values]
    assert b58encode(bytearray(range(32))) == reference(bytes(range(32)))


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize("urgent_count", [1, 20])
def test_new_urgent_event_does_not_wait_for_prefetched_candidate_batch(
    tmp_path, monkeypatch, duplicate, urgent_count
):
    engine = Orchestrator(
        Settings(data_dir=tmp_path, demo_mode=True, event_batch_size=10, _env_file=None)
    )
    engine.running = True
    for mint in ["held", *[f"candidate-{i}" for i in range(10)]]:
        engine.features.tokens[mint] = TokenState(mint=mint)
    handled = []
    persisted = []
    real_append = engine.database.append_events

    def append(events):
        result = real_append(events)
        persisted.extend(result)
        return result

    monkeypatch.setattr(engine.database, "append_events", append)
    monkeypatch.setattr(engine, "_critical_event", lambda event: event.mint == "held")

    async def handle(event, *, sequence=None):
        handled.append(event.event_id)
        if event.mint == "held":
            assert event.event_id in persisted  # A fill may only reference durable evidence.
        if len(handled) == 1:
            for index in range(urgent_count):
                urgent = MarketEvent(
                    event_id=f"urgent-{index}", source="test", kind=EventKind.TRADE, mint="held"
                )
                await engine.enqueue_event(urgent)
                if duplicate:
                    await engine.enqueue_event(urgent)
        return True

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)

    async def exercise():
        for index in range(10):
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
            await asyncio.wait_for(engine.event_queue.join(), 5)
        finally:
            engine.stop_event.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            await engine.http.close()

    try:
        asyncio.run(exercise())
        # At most one extra batch is admitted; sustained urgent traffic cannot grow the
        # in-flight batch indefinitely or starve the already admitted candidate remainder.
        interleaved = min(urgent_count, 5 if duplicate else 10)
        assert handled == [
            "candidate-0",
            *[f"urgent-{i}" for i in range(interleaved)],
            *[f"candidate-{i}" for i in range(1, 10)],
            *[f"urgent-{i}" for i in range(interleaved, urgent_count)],
        ]
        assert engine.events_processed == 10 + urgent_count
        assert not engine.event_queue._pending_sequences
        assert engine._event_batches_in_flight == 0
    finally:
        engine.database.close()


def test_urgent_batch_take_respects_priority_fifo_and_season_boundary():
    queue = SeasonEventQueue(10)
    event = MarketEvent(event_id="first", source="test", kind=EventKind.TRADE)
    queue.put_nowait((2, 1, event))
    with pytest.raises(asyncio.QueueEmpty):
        queue.get_nowait_before(1)
    queue.begin_boundary(1)
    queue.put_nowait((0, 2, event.model_copy(update={"event_id": "later-season"})))
    with pytest.raises(asyncio.QueueEmpty):
        queue.get_nowait_before(1)
    assert queue.get_nowait()[1] == 1
    queue.task_done()
    assert queue.boundary_ready()
    with pytest.raises(asyncio.QueueEmpty):
        queue.get_nowait_before(1)
    queue.end_boundary()
    queue.put_nowait((0, 3, event.model_copy(update={"event_id": "last"})))
    assert queue.get_nowait_before(1)[1] == 2
    assert queue.get_nowait_before(1)[1] == 3
    queue.task_done()
    queue.task_done()
    assert not queue._pending_sequences


@pytest.mark.parametrize("interruption", ["persistence", "handler", "cancel"])
def test_interrupted_urgent_batch_keeps_accounting_and_later_season_events(
    tmp_path, monkeypatch, interruption
):
    engine = Orchestrator(
        Settings(data_dir=tmp_path, demo_mode=True, event_batch_size=10, _env_file=None)
    )
    engine.running = True
    candidate_mints = {f"candidate-{i}" for i in range(10)}
    for mint in candidate_mints | {"held", "held-next-season"}:
        engine.features.tokens[mint] = TokenState(mint=mint)
    monkeypatch.setattr(engine, "_critical_event", lambda event: event.mint.startswith("held"))
    gaps = set()
    monkeypatch.setattr(engine, "_note_integrity_mint_gap", lambda mint, _at: gaps.add(mint))
    real_append = engine.database.append_event

    def append(event):
        if interruption == "persistence" and event.event_id == "urgent":
            raise RuntimeError("injected urgent write failure")
        return real_append(event)

    monkeypatch.setattr(engine.database, "append_event", append)

    async def exercise():
        entered = asyncio.Event()
        never = asyncio.Event()

        async def handle(event, *, sequence=None):
            if event.event_id == "candidate-0":
                await engine.enqueue_event(
                    MarketEvent(event_id="urgent", source="test", kind=EventKind.TRADE, mint="held")
                )
                engine.event_queue.begin_boundary(engine._event_sequence)
                await engine.enqueue_event(
                    MarketEvent(
                        event_id="later",
                        source="test",
                        kind=EventKind.TRADE,
                        mint="held-next-season",
                    )
                )
            elif event.event_id == "urgent":
                entered.set()
                if interruption == "handler":
                    raise RuntimeError("injected urgent handler failure")
                await never.wait()
            else:
                pytest.fail("An interrupted batch must not continue to the next event")
            return True

        async def stop_after_recovery(_now):
            if engine._event_worker_incident_active:
                engine.stop_event.set()

        monkeypatch.setattr(engine, "_handle_persisted_event", handle)
        monkeypatch.setattr(engine, "_update_queue_incident", stop_after_recovery)
        for mint in sorted(candidate_mints):
            await engine.enqueue_event(
                MarketEvent(event_id=mint, source="test", kind=EventKind.TRADE, mint=mint)
            )
        worker = asyncio.create_task(engine._event_worker_loop())
        try:
            if interruption == "cancel":
                await asyncio.wait_for(entered.wait(), 3)
                worker.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await worker
            else:
                await asyncio.wait_for(worker, 3)
            assert engine.events_processed == 1
            assert engine._event_batches_in_flight == 0
            assert not engine.event_queue._dequeued_sequences
            assert engine.event_queue.boundary_ready()
            assert engine.event_queue.empty() and engine.event_queue.qsize() == 1
            if interruption != "cancel":
                assert gaps == candidate_mints | {"held"}
            engine.event_queue.end_boundary()
            assert engine.event_queue.get_nowait()[2].event_id == "later"
            engine.event_queue.task_done()
            await asyncio.wait_for(engine.event_queue.join(), 1)
            assert not engine.event_queue._pending_sequences
        finally:
            engine.stop_event.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


def test_timing_view_uses_current_configuration_once_per_scan(settings):
    from datetime import timedelta

    from signal_arcade.models import LearningCheckpoint, RiskMode
    from test_v1104_training_history import training_fixture

    learner, database, context = training_fixture(settings)
    calls = []

    def configuration():
        calls.append(context[0])
        return context[0]

    learner.configuration_fingerprint = configuration
    try:
        for item in learner.observations.values():
            for horizon in (60, 300, 600):
                item.checkpoints[str(horizon)] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=item.created_at + timedelta(seconds=horizon),
                    net_return=0.10 if horizon == 60 else 0.01,
                )
        result = learner.hold_timing_validation(RiskMode.BALANCED)
        assert result["sample_count"] == 100
        assert result["qualified"]
        assert result["selected_horizon_seconds"] == 60
        assert len(calls) == 1
        context[0] = "different-fees"
        learner.configuration_changed()
        assert learner.hold_timing_validation(RiskMode.BALANCED)["sample_count"] == 0
    finally:
        database.close()
