from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from signal_arcade.config import Settings
from signal_arcade.event_queue import SeasonEventQueue
from signal_arcade.models import EventKind, MarketEvent, Position, QuoteCurrency
from signal_arcade.orchestrator import Orchestrator


def event(sequence: int) -> MarketEvent:
    return MarketEvent(
        event_id=str(sequence),
        source="test",
        kind=EventKind.TRADE,
        mint=f"mint-{sequence}",
        received_at=datetime.now(UTC),
    )


def test_boundary_drains_admitted_events_before_new_high_priority_arrivals() -> None:
    queue = SeasonEventQueue(maxsize=100)
    queue.put_nowait((2, 1, event(1)))
    queue.put_nowait((0, 2, event(2)))
    queue.begin_boundary(2)
    for sequence in range(3, 30):
        queue.put_nowait((0, sequence, event(sequence)))
    assert queue.get_nowait()[1] == 2
    queue.task_done()
    assert not queue.boundary_ready()
    assert queue.get_nowait()[1] == 1
    assert not queue.boundary_ready()
    queue.task_done()
    assert queue.boundary_ready()
    assert queue.empty()  # Later events are parked, not dropped.
    assert queue.qsize() == 27
    queue.end_boundary()
    for sequence in range(3, 30):
        assert queue.get_nowait()[1] == sequence
        queue.task_done()
    asyncio.run(queue.join())


def test_boundary_includes_a_critical_producer_waiting_for_capacity() -> None:
    queue = SeasonEventQueue(maxsize=1)
    queue.put_nowait((1, 1, event(1)))
    queue.admit(2)
    queue.begin_boundary(2)
    queue.get_nowait()
    queue.task_done()
    assert not queue.boundary_ready()
    queue.put_nowait((0, 2, event(2)))
    queue.get_nowait()
    queue.task_done()
    assert queue.boundary_ready()


def test_new_arrival_cannot_steal_capacity_reserved_for_old_critical_producer() -> None:
    async def scenario():
        queue = SeasonEventQueue(maxsize=1)
        queue.put_nowait((1, 1, event(1)))
        queue.admit(2)
        old = asyncio.create_task(queue.put((0, 2, event(2))))
        await asyncio.sleep(0)
        queue.begin_boundary(2)
        assert queue.get_nowait()[1] == 1
        queue.task_done()
        # Race a new arrival before the old, already-woken producer can resume.
        queue.admit(3)
        later = asyncio.create_task(queue.put((0, 3, event(3))))
        await asyncio.wait_for(old, 1)
        assert queue.get_nowait()[1] == 2
        queue.task_done()
        assert queue.boundary_ready()
        queue.end_boundary()
        await asyncio.wait_for(later, 1)
        assert queue.get_nowait()[1] == 3
        queue.task_done()
        await asyncio.wait_for(queue.join(), 1)

    asyncio.run(scenario())


def prepare_unknown_season(settings: Settings, now: datetime) -> Orchestrator:
    engine = Orchestrator(settings)
    engine.broker.initialize(QuoteCurrency.SOL, 1_000_000_000)
    engine.database.set_setting("peak_equity_lamports", 2_000_000_000)
    engine.running = True
    engine.database.set_setting("trading_enabled", True)
    position = Position(
        position_id="unknown-position",
        mint="unknown-mint",
        symbol="UNKNOWN",
        token_units=1,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=now - timedelta(hours=2),
        entry_fill_id="unknown-fill",
        last_mark_lamports=1,
        last_marked_at=now - timedelta(hours=1),
        mark_is_stale=True,
        mark_is_executable=False,
    )
    engine.broker.positions[position.mint] = position
    engine.database.save_position(position)
    asyncio.run(engine.configure_auto_new_season(True, grace_hours=1))
    engine._set_auto_new_season_clock(now - timedelta(hours=1), None, now)
    return engine


def test_unknown_inventory_has_one_persisted_bounded_deadline(settings: Settings) -> None:
    now = datetime.now(UTC)
    engine = prepare_unknown_season(settings, now)
    assert engine._auto_new_season_tick(now) is None
    deadline = engine._terminal_resolution["deadline"]
    assert engine._auto_season_progress["state"] == "waiting_for_terminal_evidence"
    for seconds in range(5, 150, 5):
        assert engine._auto_new_season_tick(now + timedelta(seconds=seconds)) is None
        assert engine._terminal_resolution["deadline"] == deadline
    asyncio.run(engine.http.close())
    engine.database.close()
    engine = Orchestrator(settings)
    assert engine._terminal_resolution["deadline"] == deadline
    for seconds in range(150, 300, 5):
        assert engine._auto_new_season_tick(now + timedelta(seconds=seconds)) is None
    assert engine._auto_new_season_tick(now + timedelta(seconds=300)) is not None
    seasons = engine.database.list_paper_seasons()
    assert len(seasons) == 2
    archived = seasons[0]
    assert archived["accounting_status"] == "incomplete_unknown"
    assert archived["comparable"] is False
    assert archived["write_off_count"] == 0
    assert archived["unresolved_inventory"][0]["terminal_disposition"] == "unknown"
    assert engine.database.get_setting("auto_new_season_terminal_resolution") is None
    assert engine._auto_new_season_tick(now + timedelta(seconds=305)) is None
    assert len(engine.database.list_paper_seasons()) == 2
    asyncio.run(engine.http.close())
    engine.database.close()


def test_live_progress_overlays_an_old_dashboard_snapshot(settings: Settings) -> None:
    now = datetime.now(UTC)
    engine = prepare_unknown_season(settings, now)
    engine._auto_new_season_tick(now)
    result = engine._snapshot_cache_response(
        (0.0, now - timedelta(minutes=5), {"season_automation": {"state": "due"}})
    )
    assert result["snapshot_age_seconds"] >= 300
    assert result["season_automation"]["state"] == "waiting_for_terminal_evidence"
    assert result["season_automation"]["age_seconds"] < 10
    asyncio.run(engine.http.close())
    engine.database.close()


def test_worker_rolls_once_between_old_and_continuously_arriving_events(settings, monkeypatch):
    now = datetime.now(UTC)
    engine = prepare_unknown_season(settings, now)
    old_season = engine.broker.season_id
    assert engine._auto_new_season_tick(now) is None
    engine._terminal_resolution["deadline"] = (now - timedelta(seconds=1)).isoformat()
    engine.database.set_setting("auto_new_season_terminal_resolution", engine._terminal_resolution)
    handled = []
    monkeypatch.setattr(engine, "_durable_event", lambda *_: False)
    monkeypatch.setattr(engine, "_event_priority", lambda _: 0)

    async def handle(row, *, sequence):
        handled.append((sequence, engine.broker.season_id))
        # Incoming traffic never becomes empty until the test's last event.
        if sequence < 6:
            following = sequence + 2
            engine.event_queue.put_nowait((0, following, event(following)))
        if len(handled) == 7:
            engine.stop_event.set()
        return True

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)
    engine.event_queue.put_nowait((2, 1, event(1)))
    engine.event_queue.put_nowait((0, 2, event(2)))
    engine.event_queue.begin_boundary(2)
    asyncio.run(asyncio.wait_for(engine._event_worker_loop(), 5))
    assert {season for seq, season in handled if seq <= 2} == {old_season}
    assert all(season == engine.broker.season_id for seq, season in handled if seq > 2)
    assert engine.broker.season_id != old_season
    assert len(engine.database.list_paper_seasons()) == 2
    assert engine._event_batches_in_flight == 0
    assert not engine.event_queue.boundary_active
    asyncio.run(engine.http.close())
    engine.database.close()
