"""Cached dashboard storage measurements must remain coherent without extra SQL."""

import copy
import time
from datetime import UTC, datetime, timedelta

import pytest
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("unknown", [False, True])
def test_cached_capacity_keeps_values_and_time_together(engine, monkeypatch, unknown):  # noqa: F811
    now = datetime.now(UTC)
    old = now - timedelta(hours=1)
    cached_storage = {
        "live_bytes": 100,
        "database_bytes": 150,
        "reclaimable_bytes": 50,
        "wal_bytes": 10,
        "max_database_bytes": 999,
        "raw_trade_retention_hours": 1,
    }
    cached = (time.monotonic(), old, {"storage": copy.deepcopy(cached_storage)})
    engine._storage_snapshot.update(
        live_bytes=200,
        database_bytes=260,
        reclaimable_bytes=60,
        wal_bytes=20,
        total_disk_bytes=280,
        wal_database_fraction=20 / 260,
        wal_pressure_state="quiet",
    )
    engine._storage_capacity_checked_at = now
    engine._storage_history_checked_at = old
    engine._storage_budget_state = "capacity_unknown" if unknown else "within_budget"
    monkeypatch.setattr(
        engine.database,
        "storage_capacity_stats",
        lambda: pytest.fail("cached storage response must not query SQLite"),
    )
    view = engine._snapshot_cache_response(cached)["storage"]
    assert view["live_bytes"] == 200
    assert view["database_bytes"] == view["live_bytes"] + view["reclaimable_bytes"]
    assert view["total_disk_bytes"] == view["database_bytes"] + view["wal_bytes"]
    assert view["maintenance"]["capacity_checked_at"] == now.isoformat()
    assert view["maintenance"]["history_checked_at"] == old.isoformat()
    assert view["maintenance"]["budget_state"] == engine._storage_budget_state
    assert view["max_database_bytes"] == engine.storage_max_bytes
    assert view["raw_trade_retention_hours"] == engine.raw_trade_retention_hours
    assert cached[2]["storage"] == cached_storage
