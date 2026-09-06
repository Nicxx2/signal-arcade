from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest
from signal_arcade.database import Database


def decisions(db, prefix, count=100):
    with db._conn:
        db._conn.executemany(
            "INSERT INTO decisions VALUES(?,?,?,?,?)",
            [
                (f"{prefix}-{i}", "mint", "pass", datetime.now(UTC).isoformat(), "x" * 15000)
                for i in range(count)
            ],
        )


def test_season_rotation_does_not_delete_or_copy_the_large_journal(tmp_path):
    path = tmp_path / "rotation.sqlite3"
    db = Database(path)
    decisions(db, "old", 1000)
    trace = []
    db._conn.set_trace_callback(trace.append)
    with db._lock, db._conn:
        db._clear_paper_tables()
        assert db._reader_conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1000
    db._conn.set_trace_callback(None)
    assert db._reader_conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
    assert not any("DELETE FROM decisions" in query for query in trace)
    assert not any("INSERT" in query and "SELECT" in query for query in trace)
    retired = db.retired_decision_tables()
    assert len(retired) == 1
    assert db._conn.execute(f"SELECT COUNT(*) FROM {retired[0]}").fetchone()[0] == 1000  # noqa: S608
    decisions(db, "new", 2)
    db.close()
    db = Database(path)
    try:
        assert db.retired_decision_tables() == retired
        assert db.prune_retired_decisions(max_rows=50)["retired_decisions"] == 50
        assert db._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2
        while db.retired_decision_tables():
            db.prune_retired_decisions(max_rows=100, max_duration_seconds=1)
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 14
        assert db.integrity_check()
    finally:
        db.close()


def test_rotation_rollback_and_empty_seasons_are_safe(tmp_path):
    db = Database(tmp_path / "rollback.sqlite3")
    try:
        decisions(db, "keep", 3)
        with pytest.raises(RuntimeError), db._conn:
            # BEGIN is explicit here: normal rollover has already archived the season,
            # which starts its transaction before the DDL handover.
            db._conn.execute("BEGIN")
            db._clear_paper_tables()
            raise RuntimeError("power loss before new season commit")
        assert db._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 3
        assert not db.retired_decision_tables()
        with db._conn:
            db._conn.execute("BEGIN")
            db._clear_paper_tables()
        with db._conn:
            db._clear_paper_tables()
        assert len(db.retired_decision_tables()) == 1
        assert db.prune_retired_decisions(stop_requested=lambda: True)["retired_decisions"] == 0
        db.set_setting("writer-still-works", True)
        assert db.get_setting("writer-still-works") is True
    finally:
        db.close()


def test_retired_cleanup_ignores_other_tables_and_current_journal(tmp_path):
    db = Database(tmp_path / "names.sqlite3")
    try:
        with db._conn:
            db._conn.execute("CREATE TABLE retired_decisions_do_not_touch (value TEXT)")
            db._conn.execute("INSERT INTO retired_decisions_do_not_touch VALUES('keep')")
        assert not db.retired_decision_tables()
        db.prune_retired_decisions()
        assert (
            db._conn.execute("SELECT value FROM retired_decisions_do_not_touch").fetchone()[0]
            == "keep"
        )
    finally:
        db.close()


def test_count_refresh_does_not_own_core_locks_and_keeps_bounded_results(tmp_path):
    db = Database(tmp_path / "counts.sqlite3")
    try:
        decisions(db, "count", 5)
        with ThreadPoolExecutor(max_workers=1) as worker, db._lock, db._reader_lock:
            counts = worker.submit(db.bounded_storage_counts, seconds=1).result(timeout=2)
        assert counts["decisions"] == 5
        assert counts["market_events"] == 0
        assert db.bounded_storage_counts(seconds=0) == {}
        assert db.oldest_retained_trade() is None
    finally:
        db.close()


def test_background_cleanup_progresses_during_normal_continuous_batches(settings):
    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    try:
        decisions(engine.database, "retire", 400)
        with engine.database._conn:
            engine.database._clear_paper_tables()
        engine._event_batches_in_flight = 1
        assert not engine._storage_market_path_busy()
        for _ in range(3):
            asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
        assert engine._storage_removed_total["retired_decisions"] > 0
        assert engine._storage_maintenance_requested
        assert engine.database._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
        assert not engine._storage_maintenance_active
    finally:
        engine.database.close()


def test_background_cleanup_waits_for_fit_and_resumes_after_it(settings, monkeypatch):
    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    engine._storage_maintenance_requested = True
    engine.learning._training_active = object()
    waits = 0
    ran = []

    async def wait(_seconds):
        nonlocal waits
        waits += 1
        if waits == 2:
            assert not ran, "cleanup competed with the fit"
            engine.learning._training_active = None

    async def cleanup(_now):
        ran.append(True)
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    monkeypatch.setattr(engine, "_run_storage_maintenance", cleanup)
    try:
        assert engine._storage_market_path_busy()
        asyncio.run(engine._storage_loop())
        assert ran == [True]
        assert not engine._storage_market_path_busy()
    finally:
        engine.database.close()


def test_many_retired_seasons_resume_after_restart_without_touching_current(tmp_path):
    path = tmp_path / "many-seasons.sqlite3"
    db = Database(path)
    try:
        # More than the bounded catalog page, and each journal straddles a delete chunk.
        for season in range(19):
            decisions(db, f"season-{season}", 3)
            with db._lock, db._conn:
                db._clear_paper_tables()
        decisions(db, "current", 2)
        assert len(db.retired_decision_tables()) == 16
        db.close()
        db = Database(path)
        reclaimed = 0
        for _ in range(60):
            result = db.prune_retired_decisions(max_rows=2, max_duration_seconds=1)
            assert 0 <= result["retired_decisions"] <= 2
            reclaimed += result["retired_decisions"]
            if not result["work_remaining"]:
                break
        assert reclaimed == 57
        assert not db.retired_decision_tables()
        assert [
            row[0]
            for row in db._conn.execute("SELECT decision_id FROM decisions ORDER BY decision_id")
        ] == ["current-0", "current-1"]
        assert db.integrity_check()
    finally:
        db.close()


def test_storage_shutdown_joins_running_cleanup_before_database_close(settings, monkeypatch):
    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    entered, finished = Event(), Event()

    def cooperative_cleanup(*_args, stop_requested, **_kwargs):
        entered.set()
        try:
            while not stop_requested():
                finished.wait(0.01)
            # This is still safe: shutdown must join us before closing the database.
            engine.database.set_setting("cleanup-cancelled", True)
            return {"work_remaining": 1}
        finally:
            finished.set()

    monkeypatch.setattr(engine.database, "prune_history", cooperative_cleanup)

    async def scenario():
        worker = asyncio.create_task(engine._run_storage_maintenance(datetime.now(UTC)))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
        finally:
            worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        assert finished.is_set()
        assert not engine._storage_maintenance_active
        assert engine.database.get_setting("cleanup-cancelled") is True

    try:
        asyncio.run(scenario())
    finally:
        engine.database.close()
