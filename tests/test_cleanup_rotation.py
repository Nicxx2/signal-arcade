"""Cleanup admission fairness without larger transactions or looser deadlines."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import copy
import random
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import pytest
import signal_arcade.database as database_module
from signal_arcade.database import Database
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, decode, encode
from signal_arcade.models import DecisionAction, EventKind, MarketEvent
from test_learning import make_decision
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("rotate", [False, True])
def test_partial_pass_rotation_prevents_category_starvation(tmp_path, monkeypatch, rotate):
    database = Database(tmp_path / "rotation.sqlite3")
    now = datetime.now(UTC)
    old = now - timedelta(days=2)
    for index in range(6):
        database.append_event(
            MarketEvent(
                event_id=f"raw-{index}",
                source="test",
                kind=EventKind.TRADE,
                mint="test-mint",
                received_at=old,
            )
        )
        decision = make_decision(old, f"mint-{index}")
        decision.action = DecisionAction.PASS
        database.save_decision(decision)
        database.record_equity(index, index)
    retained = make_decision(old, "protected-entry")
    database.save_decision(retained)
    database.append_event(
        MarketEvent(
            event_id="protected-create",
            source="test",
            kind=EventKind.CREATE,
            mint="test-mint",
            received_at=old,
        )
    )
    original = database._retention_transaction
    clock = [0.0]

    def one_query_per_pass(*args, **kwargs):
        count = original(*args, **kwargs)
        if count is not None:
            clock[0] += 0.051  # A completed query/resume consumed the original deadline.
        return count

    try:
        monkeypatch.setattr(database_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        monkeypatch.setattr(database, "_retention_transaction", one_query_per_pass)
        removed = dict.fromkeys(("raw_trades", "non_entry_decisions", "equity_points"), 0)
        for offset in range(3):
            result = database.prune_history(
                now - timedelta(days=1),
                non_entry_decision_before=now - timedelta(days=1),
                max_equity_points=1,
                max_rows_per_category=1,
                max_duration_seconds=0.05,
                category_offset=offset if rotate else 0,
            )
            assert result["work_remaining"] == 1
            for key in removed:
                removed[key] += result[key]
        assert removed == (
            {"raw_trades": 1, "non_entry_decisions": 1, "equity_points": 1}
            if rotate
            else {"raw_trades": 3, "non_entry_decisions": 0, "equity_points": 0}
        )
        assert database.get_decision(retained.decision_id) is not None
        assert "protected-create" in {event.event_id for event in database.recent_events()}
    finally:
        monkeypatch.undo()
        database.close()


@pytest.mark.parametrize("non_entry", [False, True])
@pytest.mark.parametrize("offset", [0, 1, 2, 11])
def test_rotation_keeps_bounds_and_timing_honest(tmp_path, non_entry, offset):
    database = Database(tmp_path / "bounds.sqlite3")
    now = datetime.now(UTC)
    timing = {"raw_trades_query_seconds": 999.0}
    try:
        result = database.prune_history(
            now,
            non_entry_decision_before=now if non_entry else None,
            max_rows_per_category=1,
            category_offset=offset,
            timing=timing,
        )
        assert result == {"raw_trades": 0, "non_entry_decisions": 0, "equity_points": 0}
        assert timing["completed_queries"] == (3 if non_entry else 2)
        assert sum(
            timing.get(f"{category}_query_seconds", 0) for category in result
        ) == pytest.approx(timing["query_seconds"])
        database.prune_history(
            now, timing=timing, category_offset=offset, stop_requested=lambda: True
        )
        assert timing["completed_queries"] == timing["query_seconds"] == 0
        assert all(value == 0 for key, value in timing.items() if key.endswith("query_seconds"))
        database.set_setting("after-cancel", True)
        assert database.get_setting("after-cancel") is True
    finally:
        database.close()


def test_controller_rotates_only_admitted_history_passes(engine, monkeypatch):
    # Exercise the admission controller; reader/dispatch deadlines have separate tests.
    # A throttled test worker may otherwise correctly defer before history admission.
    monkeypatch.setattr(engine.database, "maintenance_read", lambda read, **_: read())
    offsets = []

    def prune(*_args, **kwargs):
        offsets.append(kwargs["category_offset"])
        return {}

    monkeypatch.setattr(engine.database, "prune_history", prune)
    for _ in range(5):
        asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    assert offsets == [0, 1, 2, 0, 1]


def test_category_timings_fit_one_durable_storage_event(engine):
    engine._storage_counts_checked_at -= timedelta(minutes=2)
    engine._storage_history_attempted_at -= timedelta(minutes=2)
    engine._storage_diagnostic_at = 0
    asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    event = next(item for item in engine.diagnostics.events if item["kind"] == "storage")
    work = event["history_work"]
    assert work["chunk_rows"] == 50 and work["category_offset"] == 0
    assert work["at"] <= event["at"]
    assert work["categories"]["raw_trades"]["completed_queries"] == 1
    # Check incompressible timing/counter values too, not just an empty database's zeros.
    rng = random.Random(491)  # noqa: S311 -- deterministic payload edge case
    large = copy.deepcopy(event)
    large["phases"] = {key: round(rng.uniform(0, 1000), 6) for key in large["phases"]}
    large["removed"] = {key: rng.randrange(1_000_000_000) for key in large["removed"]}
    for category in large["history_work"]["categories"].values():
        for key in category:
            category[key] = round(rng.uniform(0, 1000), 6) if key.endswith("seconds") else 1
    large["history_work"]["cost_v1"] = [
        [*(round(rng.uniform(0, 1000), 6) for _ in range(3)), 50] for _ in range(3)
    ]
    for value in (event, large):
        assert engine.diagnostics._detached_event(value) == value
        packed = encode(value, max_payload=MAX_EVENT_PAYLOAD)
        assert decode(packed) == value


@pytest.mark.parametrize("offset", [-1, True, 0.5])
def test_invalid_rotation_is_rejected_before_cleanup(tmp_path, offset):
    database = Database(tmp_path / "invalid.sqlite3")
    try:
        with pytest.raises(ValueError, match="category offset"):
            database.prune_history(datetime.now(UTC), category_offset=offset)
    finally:
        database.close()
