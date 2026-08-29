from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from signal_arcade.database import Database
from signal_arcade.quota import ProviderPlan, QuotaBroker


def test_monthly_reserve_is_protected_for_critical_calls(tmp_path: Path) -> None:
    database = Database(tmp_path / "quota.sqlite3")
    broker = QuotaBroker(
        database,
        [ProviderPlan("limited", requests_per_minute=600, monthly_limit=10, reserve_fraction=0.2)],
    )

    async def exercise() -> None:
        for _ in range(8):
            assert await broker.acquire("limited")
        assert not await broker.acquire("limited")
        assert await broker.acquire("limited", critical=True)
        assert await broker.acquire("limited", critical=True)
        assert not await broker.acquire("limited", critical=True)

    asyncio.run(exercise())
    database.close()


def test_billable_plan_is_disabled_by_default(tmp_path: Path) -> None:
    database = Database(tmp_path / "quota.sqlite3")
    broker = QuotaBroker(database, [ProviderPlan("paid", 60, billable=True)])

    async def exercise() -> None:
        assert not await broker.acquire("paid")

    asyncio.run(exercise())
    database.close()


def test_monthly_plan_is_paced_and_reports_effective_rate(tmp_path: Path) -> None:
    database = Database(tmp_path / "quota.sqlite3")
    broker = QuotaBroker(
        database,
        [
            ProviderPlan(
                "paced",
                requests_per_minute=600,
                monthly_limit=43_200,
                reserve_fraction=0.1,
                pace_monthly=True,
            )
        ],
    )

    quota = broker.snapshot()["paced"]
    assert quota["requests_per_minute"] == 600
    assert quota["effective_requests_per_minute"] <= 1
    assert quota["monthly_pacing"] is True
    assert quota["reserve_fraction"] == 0.1
    database.close()


def test_provider_retry_after_blocks_immediate_reuse(tmp_path: Path) -> None:
    database = Database(tmp_path / "quota.sqlite3")
    broker = QuotaBroker(database, [ProviderPlan("limited", requests_per_minute=60)])

    async def exercise() -> None:
        assert await broker.acquire("limited")
        await broker.penalize("limited", retry_after_seconds=30)
        assert not await broker.acquire("limited")

    asyncio.run(exercise())
    database.close()


def test_bucket_never_starts_with_a_full_minute_burst(tmp_path: Path) -> None:
    database = Database(tmp_path / "quota.sqlite3")
    broker = QuotaBroker(database, [ProviderPlan("provider", requests_per_minute=300)])

    async def exercise() -> None:
        for _ in range(10):
            assert await broker.acquire("provider")
        assert not await broker.acquire("provider")

    asyncio.run(exercise())
    database.close()


def test_reconfigure_requires_explicit_billable_permission(tmp_path: Path) -> None:
    database = Database(tmp_path / "quota.sqlite3")
    broker = QuotaBroker(database, [ProviderPlan("paid", 60, billable=True)])

    async def exercise() -> None:
        assert not await broker.acquire("paid")
        await broker.reconfigure(
            [ProviderPlan("paid", 60, monthly_limit=100, billable=True)],
            allow_billable=True,
        )
        assert await broker.acquire("paid")

    asyncio.run(exercise())
    database.close()


def test_retry_after_is_capped_to_five_minutes(tmp_path: Path) -> None:
    database = Database(tmp_path / "quota.sqlite3")
    broker = QuotaBroker(database, [ProviderPlan("limited", requests_per_minute=60)])

    async def exercise() -> None:
        with patch("signal_arcade.quota.time.monotonic", return_value=100.0):
            await broker.penalize("limited", retry_after_seconds=10_000)
        bucket = broker._buckets["limited"]  # noqa: SLF001 - focused governor invariant
        assert bucket.unavailable_until == 400.0

    asyncio.run(exercise())
    database.close()
