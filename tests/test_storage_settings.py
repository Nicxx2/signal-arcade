"""Storage policy edits are atomic, conflict-aware and independent of cleanup/proof."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from signal_arcade.api import create_app
from test_probe_retention import engine  # noqa: F401


def test_concurrent_storage_saves_and_restart(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        before = app.state.orchestrator.learning.coverage_policy
        barrier = threading.Barrier(2)

        def save(gb):
            barrier.wait(timeout=5)
            return client.put(
                "/api/v1/storage-settings",
                json={
                    "max_database_gb": gb,
                    "raw_trade_retention_hours": 24,
                    "expected_revision": 0,
                },
            )

        with ThreadPoolExecutor(max_workers=2) as workers:
            replies = list(workers.map(save, [16, 30]))
        assert sorted(r.status_code for r in replies) == [200, 409]
        winner = next(r.json() for r in replies if r.status_code == 200)
        assert winner["policy_revision"] == 1
        assert app.state.orchestrator.learning.coverage_policy == before
        assert (
            app.state.orchestrator.storage_policy()["max_database_bytes"]
            == winner["max_database_bytes"]
        )
    with TestClient(create_app(settings)) as client:
        policy = client.get("/api/v1/snapshot").json()["storage"]
        assert policy["policy_revision"] == 1
        assert policy["max_database_bytes"] == winner["max_database_bytes"]
        body = {
            "max_database_gb": winner["max_database_bytes"] / 1024**3,
            "raw_trade_retention_hours": 24,
            "expected_revision": 1,
        }
        assert client.put("/api/v1/storage-settings", json=body).json()["policy_revision"] == 1
        body["expected_revision"] = 0
        assert client.put("/api/v1/storage-settings", json=body).status_code == 409


@pytest.mark.parametrize("revision", [-1, True, "0", 0.0])
def test_revision_validation_has_no_side_effects(settings, revision):
    app = create_app(settings)
    with TestClient(app) as client:
        result = client.put(
            "/api/v1/storage-settings",
            json={
                "max_database_gb": 30,
                "raw_trade_retention_hours": 24,
                "expected_revision": revision,
            },
        )
        assert result.status_code == 422
        assert app.state.orchestrator.storage_policy()["policy_revision"] == 0


def test_legacy_save_still_advances_revision_and_upgrade_blocks_saves(settings, monkeypatch):
    app = create_app(settings)
    with TestClient(app) as client:
        body = {"max_database_gb": 16, "raw_trade_retention_hours": 24}
        assert client.put("/api/v1/storage-settings", json=body).json()["policy_revision"] == 1
        monkeypatch.setattr(
            type(app.state.orchestrator), "maintenance_active", property(lambda _: True)
        )
        body.update(max_database_gb=30, expected_revision=1)
        assert client.put("/api/v1/storage-settings", json=body).status_code == 409
        assert app.state.orchestrator.storage_policy()["policy_revision"] == 1


def test_save_does_not_clear_unknown_measurement_or_run_cleanup(engine, monkeypatch):  # noqa: F811
    engine._storage_budget_state = "capacity_unknown"
    stamp = engine._storage_capacity_checked_at
    original = dict(engine._storage_snapshot)
    for name in (
        "prune_history",
        "enforce_storage_budget",
        "storage_stats",
        "storage_capacity_stats",
    ):
        monkeypatch.setattr(
            engine.database, name, lambda *_a, **_k: pytest.fail("inline cleanup/read")
        )
    result = asyncio.run(engine.configure_storage(30 * 1024**3, 24))
    assert result["policy_revision"] == 1
    assert result["maintenance"]["budget_state"] == "capacity_unknown"
    assert engine._storage_capacity_checked_at == stamp
    assert engine._storage_snapshot == original
    assert engine.database.get_setting("storage_policy_revision") == 1


def test_failed_commit_changes_neither_settings_nor_runtime(engine, monkeypatch):  # noqa: F811
    before = engine.storage_policy()
    original = engine.database._upsert_settings

    def fail_after_sql(*args):
        original(*args)
        raise RuntimeError("injected transaction failure")

    monkeypatch.setattr(engine.database, "_upsert_settings", fail_after_sql)
    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(engine.configure_storage(30 * 1024**3, 24))
    assert engine.storage_policy() == before
    assert engine.database.get_setting("storage_max_bytes") is None
    assert engine.database.get_setting("raw_trade_retention_hours") is None
    assert engine.database.get_setting("storage_policy_revision") is None


def test_repeated_cancellation_keeps_mutation_lock_until_policy_is_coherent(engine, monkeypatch):  # noqa: F811
    started, release = threading.Event(), threading.Event()
    original = engine.database.set_settings

    def delayed(values):
        started.set()
        assert release.wait(timeout=10)
        original(values)

    monkeypatch.setattr(engine.database, "set_settings", delayed)

    async def exercise():
        async def request():
            async with engine.maintenance_mutation_lock:
                return await engine.configure_storage(30 * 1024**3, 24)

        task = asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert engine.maintenance_mutation_lock.locked()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not engine.maintenance_mutation_lock.locked()
        assert (
            engine.storage_max_bytes
            == engine.database.get_setting("storage_max_bytes")
            == 30 * 1024**3
        )
        assert (
            engine.storage_policy()["policy_revision"]
            == engine.database.get_setting("storage_policy_revision")
            == 1
        )

    asyncio.run(exercise())


def test_returning_to_an_old_value_does_not_make_an_old_revision_valid(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        original = app.state.orchestrator.storage_policy()
        first = {
            "max_database_gb": 30,
            "raw_trade_retention_hours": 24,
            "expected_revision": 0,
        }
        assert client.put("/api/v1/storage-settings", json=first).status_code == 200
        restored = {
            "max_database_gb": original["max_database_bytes"] / 1024**3,
            "raw_trade_retention_hours": original["raw_trade_retention_hours"],
            "expected_revision": 1,
        }
        assert client.put("/api/v1/storage-settings", json=restored).json()["policy_revision"] == 2
        assert client.put("/api/v1/storage-settings", json=first).status_code == 409
        current = app.state.orchestrator.storage_policy()
        assert current["max_database_bytes"] == original["max_database_bytes"]
        assert current["raw_trade_retention_hours"] == original["raw_trade_retention_hours"]
        assert current["policy_revision"] == 2


def test_cancelled_failed_save_rolls_back_and_releases_ownership(engine, monkeypatch):  # noqa: F811
    started, release = threading.Event(), threading.Event()
    before = engine.storage_policy()
    original = engine.database._upsert_settings

    def fail_after_sql(*args):
        original(*args)
        started.set()
        assert release.wait(timeout=10)
        raise RuntimeError("injected commit failure after cancellation")

    monkeypatch.setattr(engine.database, "_upsert_settings", fail_after_sql)

    async def exercise():
        async def request():
            async with engine.maintenance_mutation_lock:
                return await engine.configure_storage(30 * 1024**3, 24)

        task = asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            assert engine.maintenance_mutation_lock.locked()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not engine.maintenance_mutation_lock.locked()
        assert engine.storage_policy() == before
        for key in ("storage_max_bytes", "raw_trade_retention_hours", "storage_policy_revision"):
            assert engine.database.get_setting(key) is None

    asyncio.run(exercise())
