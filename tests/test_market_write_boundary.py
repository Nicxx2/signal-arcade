import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event, RLock, get_ident

import pytest
from signal_arcade.database import Database
from signal_arcade.models import EventKind, MarketEvent


@pytest.mark.parametrize("batch", [False, True])
def test_committed_market_write_invalidates_counts_before_handing_writer_to_maintenance(
    tmp_path, batch
):
    database = Database(tmp_path / "market.sqlite3")
    assert database.storage_stats()["market_events"] == 0
    original_lock = database._lock
    released, reader_ready, release_reader = Event(), Event(), Event()
    writer_ident = []
    observed = []

    class HandoffLock:
        """Force the real scheduling window between commit and a subsequent lock request."""

        def __init__(self):
            self.lock = RLock()
            self.depth = 0

        def __enter__(self):
            self.lock.acquire()
            if writer_ident and get_ident() == writer_ident[0]:
                self.depth += 1
            return self

        def __exit__(self, *_args):
            is_writer = bool(writer_ident and get_ident() == writer_ident[0])
            if is_writer:
                self.depth -= 1
            boundary = is_writer and self.depth == 0 and not released.is_set()
            self.lock.release()
            if boundary:
                released.set()
                assert reader_ready.wait(5)

    database._lock = HandoffLock()

    def maintenance_reader():
        assert released.wait(5)
        with database._lock:
            try:
                committed = database._conn.execute("SELECT COUNT(*) FROM market_events").fetchone()[
                    0
                ]
                observed.append((committed, database.storage_stats()["market_events"]))
            finally:
                reader_ready.set()
            assert release_reader.wait(5)

    def append():
        writer_ident.append(get_ident())
        events = [MarketEvent(event_id="one", source="fixture", kind=EventKind.TRADE, mint="one")]
        if batch:
            events.append(events[0])  # A duplicate is not a second durable observation.
            events.append(
                MarketEvent(event_id="two", source="fixture", kind=EventKind.TRADE, mint="two")
            )
            return database.append_events(events)
        return {"one"} if database.append_event(events[0]) else set()

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            reader = workers.submit(maintenance_reader)
            writer = workers.submit(append)
            try:
                assert reader_ready.wait(5)
                expected = 2 if batch else 1
                # Once another worker can read the committed rows, cached counts cannot
                # still describe the previous transaction. No arbitrary sleep is needed.
                assert observed == [(expected, expected)]
                assert writer.result(timeout=2) == ({"one", "two"} if batch else {"one"})
            finally:
                release_reader.set()
            reader.result(timeout=5)
            writer.result(timeout=5)
    finally:
        database._lock = original_lock
        database.close()


def test_market_batch_failure_rolls_back_without_corrupting_storage_cache(tmp_path):
    database = Database(tmp_path / "rollback.sqlite3")
    try:
        first = MarketEvent(event_id="first", source="fixture", kind=EventKind.TRADE, mint="one")
        invalid = MarketEvent(
            event_id="invalid", source="fixture", kind=EventKind.TRADE, mint="two"
        )
        invalid.payload["unserializable"] = object()
        assert database.storage_stats()["market_events"] == 0
        revision = database._storage_revision
        with pytest.raises(TypeError):
            database.append_events([first, invalid])
        assert database.recent_events() == []
        assert database.storage_stats()["market_events"] == 0
        assert database._storage_revision == revision
        assert database.append_event(first)
        assert database.storage_stats()["market_events"] == 1
        revision = database._storage_revision
        assert database.append_events([first, first]) == set()
        assert database._storage_revision == revision
        assert database.storage_stats()["market_events"] == 1
    finally:
        database.close()


def test_failed_market_commit_preserves_prior_events_and_rebuilds_invalidated_counts(tmp_path):
    database = Database(tmp_path / "commit-failure.sqlite3")
    try:
        existing = MarketEvent(
            event_id="existing", source="fixture", kind=EventKind.TRADE, mint="a"
        )
        pending = MarketEvent(event_id="pending", source="fixture", kind=EventKind.TRADE, mint="b")
        assert database.append_event(existing)
        assert database.storage_stats()["market_events"] == 1

        def refuse_commit(action, argument, *_args):
            return (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_TRANSACTION and argument == "COMMIT"
                else sqlite3.SQLITE_OK
            )

        database._conn.set_authorizer(refuse_commit)
        try:
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                database.append_events([existing, pending])
        finally:
            database._conn.set_authorizer(None)
        assert not database._conn.in_transaction
        assert {event.event_id for event in database.recent_events()} == {"existing"}
        # Invalidation before a failed COMMIT is harmless: a fresh count sees the rollback.
        assert database.storage_stats()["market_events"] == 1
        assert database.append_events([existing, pending]) == {"pending"}
        assert database.storage_stats()["market_events"] == 2
    finally:
        database.close()
