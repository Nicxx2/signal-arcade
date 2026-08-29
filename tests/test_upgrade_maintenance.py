from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from signal_arcade.api import create_app
from signal_arcade.config import Settings
from signal_arcade.models import OrderStatus, PaperOrder, Position, QuoteCurrency, Side
from signal_arcade.orchestrator import Orchestrator


def _settings(path: Path) -> Settings:
    return Settings(
        data_dir=path,
        demo_mode=True,
        entry_latency_ms=0,
        exit_latency_ms=0,
        _env_file=None,
    )


def _wait_for_maintenance(client: TestClient, state: str = "ready") -> dict[str, object]:
    for _ in range(300):
        operation = client.get("/api/v1/maintenance-operation").json()
        if operation and operation["state"] == state:
            return operation
        time.sleep(0.01)
    raise AssertionError(f"maintenance operation did not reach {state}")


def test_upgrade_preparation_freezes_then_restores_runtime_without_resetting_data(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(_settings(tmp_path))

    async def scenario() -> None:
        await orchestrator.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000)
        orchestrator.running = True
        orchestrator.database.set_setting("trading_enabled", True)
        await orchestrator.configure_auto_new_season(True, 4)
        eligible_since = datetime.now(UTC) - timedelta(hours=1)
        orchestrator._set_auto_new_season_eligible_since(eligible_since)  # noqa: SLF001
        position = Position(
            position_id="open-position",
            mint="open-mint",
            symbol="OPEN",
            token_units=1,
            entry_cost_lamports=100_000_000,
            book_value_lamports=100_000_000,
            opened_at=datetime.now(UTC),
            entry_fill_id="entry-fill",
        )
        orchestrator.broker.positions[position.mint] = position
        orchestrator.database.save_position(position)
        pending = PaperOrder(
            order_id="pending-order",
            mint="pending-mint",
            symbol="PENDING",
            side=Side.BUY,
            requested_sol_lamports=25_000_000,
            fill_after=datetime.now(UTC) + timedelta(minutes=1),
        )
        orchestrator.broker.pending[pending.order_id] = pending
        orchestrator.database.save_order(pending)
        download = asyncio.create_task(asyncio.Event().wait())
        orchestrator.ai_lab.download_tasks["qwen3.5:2b"] = download
        orchestrator.ai_lab.downloads["qwen3.5:2b"] = {
            "model": "qwen3.5:2b",
            "status": "downloading",
            "completed_bytes": 10,
            "total_bytes": 100,
            "progress_fraction": 0.1,
            "message": "Downloading",
            "error": None,
        }

        first = await orchestrator.begin_upgrade_preparation()
        duplicate = await orchestrator.begin_upgrade_preparation()
        assert duplicate["operation_id"] == first["operation_id"]
        assert orchestrator._maintenance_operation_task is not None  # noqa: SLF001
        await asyncio.wait_for(orchestrator._maintenance_operation_task, timeout=3)  # noqa: SLF001

        ready = orchestrator.maintenance_operation_status()
        assert ready is not None
        assert ready["state"] == "ready"
        assert ready["previous_running"] is True
        assert orchestrator.running is False
        assert orchestrator.database.get_setting("trading_enabled") is True
        assert orchestrator.database.get_setting("auto_new_season_eligible_since") is None
        assert orchestrator.broker.initialized is True
        assert orchestrator.broker.starting_lamports == 1_000_000_000
        assert set(orchestrator.broker.positions) == {"open-mint"}
        assert orchestrator.broker.pending == {}
        cancelled_orders = orchestrator.database.list_orders([OrderStatus.CANCELLED.value])
        assert [order.order_id for order in cancelled_orders] == ["pending-order"]
        assert cancelled_orders[0].failure_reason == "upgrade_preparation"
        assert orchestrator.ai_lab.maintenance_paused is True
        assert ready["cancelled_pending_orders"] == 1
        assert ready["interrupted_ai_downloads"] == 1
        assert download.cancelled() is True
        assert orchestrator.ai_lab.downloads["qwen3.5:2b"]["status"] == "error"

        cancelled = await orchestrator.cancel_upgrade_preparation()
        assert cancelled["state"] == "cancelled"
        assert orchestrator.running is True
        assert orchestrator.ai_lab.maintenance_paused is False
        restored = orchestrator._auto_new_season_eligible_since  # noqa: SLF001
        assert restored is not None
        restored_elapsed = (datetime.now(UTC) - restored).total_seconds()
        assert 3_590 <= restored_elapsed <= 3_610

        await orchestrator.http.close()

    try:
        asyncio.run(scenario())
    finally:
        orchestrator.database.close()


def test_ready_preparation_reconciles_as_completed_after_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = Orchestrator(settings)

    async def prepare() -> None:
        await first.setup_portfolio(QuoteCurrency.USDC, 25_000_000)
        first.running = True
        first.database.set_setting("trading_enabled", True)
        operation = await first.begin_upgrade_preparation()
        assert operation["previous_running"] is True
        assert first._maintenance_operation_task is not None  # noqa: SLF001
        await asyncio.wait_for(first._maintenance_operation_task, timeout=3)  # noqa: SLF001
        await first.http.close()

    asyncio.run(prepare())
    first.database.close()

    restarted = Orchestrator(settings)
    try:
        operation = restarted.maintenance_operation_status()
        assert operation is not None
        assert operation["state"] == "completed"
        assert operation["stage"] == "restarted"
        assert restarted.running is True
        assert restarted.broker.quote_currency == QuoteCurrency.USDC
        assert restarted.broker.starting_lamports == 25_000_000
        assert restarted.database.get_setting("trading_enabled") is True
        asyncio.run(restarted.http.close())
    finally:
        restarted.database.close()


def test_interrupted_preparation_cancels_unfilled_orders_on_recovery(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = Orchestrator(settings)

    async def arrange() -> None:
        await first.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000)
        first.running = True
        first.database.set_setting("trading_enabled", True)
        pending = PaperOrder(
            order_id="interrupted-pending",
            mint="pending-mint",
            symbol="PENDING",
            side=Side.BUY,
            requested_sol_lamports=25_000_000,
            fill_after=datetime.now(UTC) + timedelta(minutes=1),
        )
        first.broker.pending[pending.order_id] = pending
        first.database.save_order(pending)
        now = datetime.now(UTC).isoformat()
        first.database.set_setting(
            "maintenance_operation",
            {
                "operation_id": "interrupted-upgrade",
                "kind": "upgrade",
                "state": "running",
                "stage": "settling_paper_actions",
                "detail": "Preparation was interrupted.",
                "started_at": now,
                "updated_at": now,
                "ready_at": None,
                "completed_at": None,
                "prepared_version": "1.6.6",
                "restarted_version": None,
                "previous_running": True,
                "auto_season_remaining_seconds": None,
                "cancelled_pending_orders": 0,
                "interrupted_ai_downloads": 0,
            },
        )
        await first.http.close()

    asyncio.run(arrange())
    first.database.close()

    restarted = Orchestrator(settings)
    try:
        operation = restarted.maintenance_operation_status()
        assert operation is not None
        assert operation["state"] == "completed"
        assert operation["cancelled_pending_orders"] == 1
        assert restarted.broker.pending == {}
        cancelled = restarted.database.list_orders([OrderStatus.CANCELLED.value])
        assert [order.failure_reason for order in cancelled] == ["interrupted_upgrade_preparation"]
        asyncio.run(restarted.http.close())
    finally:
        restarted.database.close()


def test_upgrade_preparation_failure_restores_normal_operation(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    orchestrator = Orchestrator(_settings(tmp_path))

    async def scenario() -> None:
        await orchestrator.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000)
        orchestrator.running = True
        orchestrator.database.set_setting("trading_enabled", True)
        monkeypatch.setattr(orchestrator.database, "health_check", lambda: False)
        await orchestrator.begin_upgrade_preparation()
        assert orchestrator._maintenance_operation_task is not None  # noqa: SLF001
        await asyncio.wait_for(orchestrator._maintenance_operation_task, timeout=3)  # noqa: SLF001

        operation = orchestrator.maintenance_operation_status()
        assert operation is not None
        assert operation["state"] == "failed"
        assert orchestrator.maintenance_active is False
        assert orchestrator.running is True
        assert orchestrator.ai_lab.maintenance_paused is False
        assert orchestrator.database.get_setting("trading_enabled") is True
        await orchestrator.http.close()

    try:
        asyncio.run(scenario())
    finally:
        orchestrator.database.close()


def test_maintenance_api_confirms_blocks_mutations_and_resumes_after_update(
    settings: Settings,
) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/portfolio/setup",
                json={"quote_currency": "SOL", "starting_amount": "1"},
            ).status_code
            == 200
        )
        assert client.post("/api/v1/engine/start").status_code == 200
        assert (
            client.post(
                "/api/v1/maintenance/prepare",
                json={"confirmation": "wrong"},
            ).status_code
            == 400
        )

        accepted = client.post(
            "/api/v1/maintenance/prepare",
            json={"confirmation": "PREPARE FOR UPGRADE"},
        )
        assert accepted.status_code == 202
        ready = _wait_for_maintenance(client)
        assert ready["state"] == "ready"
        snapshot = client.get("/api/v1/snapshot").json()
        assert snapshot["running"] is False
        assert snapshot["maintenance_operation"]["state"] == "ready"
        assert client.put("/api/v1/risk", json={"mode": "safe"}).status_code == 409
        assert client.post("/api/v1/engine/start").status_code == 409
        assert client.get("/api/v1/health").json()["ok"] is True

        resumed = client.post("/api/v1/maintenance/cancel")
        assert resumed.status_code == 200
        assert resumed.json()["state"] == "cancelled"
        assert client.get("/api/v1/snapshot").json()["running"] is True


def test_prepared_testclient_restart_preserves_engine_preference(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/portfolio/setup",
            json={"quote_currency": "SOL", "starting_amount": "1"},
        ).raise_for_status()
        client.post("/api/v1/engine/start").raise_for_status()
        client.post(
            "/api/v1/maintenance/prepare",
            json={"confirmation": "PREPARE FOR UPGRADE"},
        ).raise_for_status()
        _wait_for_maintenance(client)

    with TestClient(create_app(settings)) as restarted:
        snapshot = restarted.get("/api/v1/snapshot").json()
        assert snapshot["maintenance_operation"]["state"] == "completed"
        assert snapshot["running"] is True
        assert snapshot["portfolio"]["starting_lamports"] == 1_000_000_000
