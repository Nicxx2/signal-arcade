from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from signal_arcade.config import Settings
from signal_arcade.database import Database
from signal_arcade.models import (
    DecisionAction,
    EventKind,
    LearningObservation,
    MarketEvent,
    Position,
    QuoteCurrency,
    RiskMode,
)
from signal_arcade.orchestrator import (
    AUTO_NEW_SEASON_GRACE_SECONDS,
    AUTO_NEW_SEASON_STARTUP_DATA_GRACE_SECONDS,
    Orchestrator,
)


def season_summary(*, open_positions: int = 0) -> dict[str, int | float]:
    return {
        "ending_equity_minor": 500_000_000,
        "last_known_ending_equity_minor": 520_000_000,
        "peak_equity_minor": 1_000_000_000,
        "realized_pnl_minor": -500_000_000,
        "net_pnl_minor": -500_000_000,
        "total_fees_minor": 1_000_000,
        "closed_trades": 3,
        "wins": 1,
        "losses": 2,
        "break_even": 0,
        "ending_drawdown_fraction": 0.5,
        "open_positions": open_positions,
    }


def learning_observation(now: datetime) -> LearningObservation:
    return LearningObservation(
        observation_id="lesson-kept",
        decision_id="decision-kept",
        mint="mint-kept",
        symbol="KEPT",
        created_at=now,
        baseline_action=DecisionAction.ENTER,
        risk_mode=RiskMode.BALANCED,
        baseline_edge_index=0.08,
        baseline_composite=80,
        features={"opportunity": 0.8},
        token_units=1,
        entry_cost_lamports=1,
        entry_price_impact_fraction=0,
        fee_bps=125,
        season_id="season-one",
    )


def dormant_position(now: datetime) -> Position:
    return Position(
        position_id="dormant-position",
        mint="dormant-mint",
        symbol="DORMANT",
        token_units=1,
        entry_cost_lamports=100_000_000,
        book_value_lamports=100_000_000,
        opened_at=now - timedelta(days=2),
        entry_fill_id="entry-fill",
        last_mark_lamports=20_000_000,
        unrealized_pnl_lamports=-80_000_000,
        last_marked_at=now - timedelta(days=1),
        mark_is_stale=True,
        mark_is_executable=False,
    )


def test_atomic_rollover_archives_and_refunds_without_erasing_learning(tmp_path: Path) -> None:
    database = Database(tmp_path / "rollover.sqlite3")
    now = datetime(2026, 8, 27, 12, tzinfo=UTC)
    database.initialize_portfolio("season-one", 1_000_000_000, "SOL")
    database.save_learning_observation(learning_observation(now))
    database.set_setting("auto_new_season_eligible_since", now.isoformat())

    database.rollover_paper_state(
        season_summary=season_summary(open_positions=1),
        next_season_id="season-two",
        starting_minor=1_000_000_000,
        quote_currency="SOL",
        rolled_over_at=now + timedelta(days=1),
    )

    seasons = database.list_paper_seasons()
    assert [(item["season_number"], item["status"]) for item in seasons] == [
        (1, "completed"),
        (2, "current"),
    ]
    assert seasons[0]["open_positions"] == 1
    assert seasons[1]["starting_minor"] == 1_000_000_000
    assert database.ledger_balance("cash") == 1_000_000_000
    assert database.get_setting("season_id") == "season-two"
    assert database.get_setting("trading_enabled") is True
    assert database.get_setting("auto_new_season_eligible_since") is None
    assert [item.observation_id for item in database.list_learning_observations()] == [
        "lesson-kept"
    ]
    database.close()


def test_atomic_rollover_restores_old_season_if_new_season_insert_fails(tmp_path: Path) -> None:
    database = Database(tmp_path / "rollover-failure.sqlite3")
    now = datetime(2026, 8, 27, 12, tzinfo=UTC)
    database.initialize_portfolio("season-one", 1_000_000_000, "SOL")
    database._conn.executescript(  # noqa: SLF001 - intentional transaction fault injection
        """
        CREATE TRIGGER reject_rollover BEFORE INSERT ON paper_seasons
        WHEN NEW.season_id = 'season-fails'
        BEGIN SELECT RAISE(ABORT, 'injected rollover failure'); END;
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="injected rollover failure"):
        database.rollover_paper_state(
            season_summary=season_summary(),
            next_season_id="season-fails",
            starting_minor=1_000_000_000,
            quote_currency="SOL",
            rolled_over_at=now,
        )

    seasons = database.list_paper_seasons()
    assert [(item["season_id"], item["status"]) for item in seasons] == [("season-one", "current")]
    assert database.ledger_balance("cash") == 1_000_000_000
    assert database.get_setting("season_id") == "season-one"
    assert database.get_setting("auto_new_season_last_to") is None
    database.close()


def test_auto_season_waits_full_grace_then_rolls_dormant_season(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    started = datetime.now(UTC)
    orchestrator.broker.initialize(QuoteCurrency.SOL, 1_000_000_000)
    position = dormant_position(started)
    orchestrator.broker.positions[position.mint] = position
    orchestrator.database.save_position(position)
    orchestrator.database.save_learning_observation(learning_observation(started))
    orchestrator.database.set_setting("peak_equity_lamports", 2_000_000_000)
    orchestrator.running = True
    orchestrator.database.set_setting("trading_enabled", True)
    asyncio.run(orchestrator.configure_auto_new_season(True))

    assert orchestrator._auto_new_season_tick(started) is None  # noqa: SLF001
    status = orchestrator.season_automation_status(
        orchestrator.broker.snapshot(RiskMode.BALANCED, persist_peak=False),
        started + timedelta(hours=23),
    )
    assert status["state"] == "countdown"
    assert status["remaining_seconds"] == pytest.approx(3600)
    assert (
        orchestrator._auto_new_season_tick(  # noqa: SLF001
            started + timedelta(seconds=AUTO_NEW_SEASON_GRACE_SECONDS - 1)
        )
        is None
    )

    rollover = orchestrator._auto_new_season_tick(  # noqa: SLF001
        started + timedelta(seconds=AUTO_NEW_SEASON_GRACE_SECONDS + 1)
    )

    assert rollover is not None
    assert rollover["previous_season_id"] != rollover["next_season_id"]
    assert orchestrator.running is True
    assert orchestrator.broker.positions == {}
    assert orchestrator.broker.cash_lamports == 1_000_000_000
    assert orchestrator.broker.starting_lamports == 1_000_000_000
    assert [item.observation_id for item in orchestrator.database.list_learning_observations()] == [
        "lesson-kept"
    ]
    assert [item["status"] for item in orchestrator.database.list_paper_seasons()] == [
        "completed",
        "current",
    ]
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_auto_season_countdown_resets_on_stop_revival_or_unhealthy_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))
    now = datetime.now(UTC)
    orchestrator.broker.initialize(QuoteCurrency.SOL, 1_000_000_000)
    orchestrator.database.set_setting("peak_equity_lamports", 2_000_000_000)
    orchestrator.running = True
    asyncio.run(orchestrator.configure_auto_new_season(True))

    assert orchestrator._auto_new_season_tick(now) is None  # noqa: SLF001
    assert orchestrator._auto_new_season_eligible_since == now  # noqa: SLF001

    orchestrator.running = False
    assert orchestrator._auto_new_season_tick(now + timedelta(hours=1)) is None  # noqa: SLF001
    assert orchestrator._auto_new_season_eligible_since is None  # noqa: SLF001

    orchestrator.running = True
    position = dormant_position(now).model_copy(
        update={
            "last_marked_at": datetime.now(UTC),
            "mark_is_stale": False,
            "mark_is_executable": True,
        }
    )
    orchestrator.broker.positions[position.mint] = position
    status = orchestrator.season_automation_status(
        orchestrator.broker.snapshot(RiskMode.BALANCED, persist_peak=False), now
    )
    assert status["state"] == "managing_positions"
    assert orchestrator._auto_new_season_tick(now + timedelta(hours=2)) is None  # noqa: SLF001

    orchestrator.broker.positions.clear()
    monkeypatch.setattr(orchestrator, "_rollover_market_data_healthy", lambda _now: False)
    assert orchestrator._auto_new_season_tick(now + timedelta(hours=3)) is None  # noqa: SLF001
    assert orchestrator._auto_new_season_eligible_since is None  # noqa: SLF001
    status = orchestrator.season_automation_status(
        orchestrator.broker.snapshot(RiskMode.BALANCED, persist_peak=False), now
    )
    assert status["state"] == "waiting_for_data"

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_restart_briefly_preserves_countdown_but_never_rolls_without_live_data(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    database = Database(tmp_path / "signal_arcade.sqlite3")
    database.initialize_portfolio("season-one", 1_000_000_000, "SOL")
    database.set_settings(
        {
            "peak_equity_lamports": 2_000_000_000,
            "trading_enabled": True,
            "auto_new_season_enabled": True,
            "auto_new_season_eligible_since": (now - timedelta(hours=23)).isoformat(),
        }
    )
    database.close()

    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=False, _env_file=None))
    assert orchestrator.running is True
    assert orchestrator._auto_new_season_tick(now) is None  # noqa: SLF001
    assert orchestrator._auto_new_season_eligible_since == now - timedelta(hours=23)  # noqa: SLF001
    assert len(orchestrator.database.list_paper_seasons()) == 1

    after_grace = now + timedelta(seconds=AUTO_NEW_SEASON_STARTUP_DATA_GRACE_SECONDS + 1)
    assert orchestrator._auto_new_season_tick(after_grace) is None  # noqa: SLF001
    assert orchestrator._auto_new_season_eligible_since is None  # noqa: SLF001
    assert len(orchestrator.database.list_paper_seasons()) == 1

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_due_rollover_waits_for_queued_and_inflight_market_evidence(tmp_path: Path) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))
    now = datetime.now(UTC)
    orchestrator.broker.initialize(QuoteCurrency.SOL, 1_000_000_000)
    orchestrator.database.set_setting("peak_equity_lamports", 2_000_000_000)
    orchestrator.running = True
    asyncio.run(orchestrator.configure_auto_new_season(True))
    orchestrator._set_auto_new_season_eligible_since(  # noqa: SLF001
        now - timedelta(seconds=AUTO_NEW_SEASON_GRACE_SECONDS)
    )
    orchestrator._route_retry_at["old-mint"] = now + timedelta(hours=1)  # noqa: SLF001
    orchestrator._route_retry_delay_seconds["old-mint"] = 3_600  # noqa: SLF001

    event = MarketEvent(
        event_id="queued-before-rollover",
        source="test",
        kind=EventKind.TRADE,
        mint="queued-mint",
        received_at=now,
    )
    orchestrator.event_queue.put_nowait((2, 1, event))
    assert orchestrator._auto_new_season_tick(now) is None  # noqa: SLF001
    queued = orchestrator.event_queue.get_nowait()
    orchestrator.event_queue.task_done()

    orchestrator._event_batches_in_flight = 1  # noqa: SLF001
    assert orchestrator._auto_new_season_tick(now + timedelta(seconds=1)) is None  # noqa: SLF001
    orchestrator._event_batches_in_flight = 0  # noqa: SLF001

    rollover = orchestrator._auto_new_season_tick(now + timedelta(seconds=2))  # noqa: SLF001
    assert rollover is not None
    assert queued[2].event_id == event.event_id
    assert orchestrator._route_retry_at == {}  # noqa: SLF001
    assert orchestrator._route_retry_delay_seconds == {}  # noqa: SLF001
    assert len(orchestrator.database.list_paper_seasons()) == 2

    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_failed_policy_save_does_not_partially_change_in_memory_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))

    def fail_settings(_values: dict[str, object]) -> None:
        raise sqlite3.OperationalError("injected settings failure")

    monkeypatch.setattr(orchestrator.database, "set_settings", fail_settings)
    with pytest.raises(sqlite3.OperationalError, match="injected settings failure"):
        asyncio.run(orchestrator.configure_auto_new_season(True))

    assert orchestrator.auto_new_season_enabled is False
    assert orchestrator._auto_new_season_eligible_since is None  # noqa: SLF001
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def test_custom_grace_is_bounded_persistent_and_cannot_change_mid_countdown(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    orchestrator = Orchestrator(settings)
    configured = asyncio.run(orchestrator.configure_auto_new_season(False, 4))
    assert configured["grace_seconds"] == 4 * 60 * 60
    enabled = asyncio.run(orchestrator.configure_auto_new_season(True, 4))
    assert enabled["enabled"] is True
    with pytest.raises(ValueError, match="turn automatic seasons off"):
        asyncio.run(orchestrator.configure_auto_new_season(True, 2))
    with pytest.raises(ValueError, match="between 1 and 24 hours"):
        asyncio.run(orchestrator.configure_auto_new_season(False, 0))
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()

    restarted = Orchestrator(settings)
    status = restarted.season_automation_status(
        restarted.broker.snapshot(RiskMode.BALANCED, persist_peak=False)
    )
    assert status["grace_seconds"] == 4 * 60 * 60
    asyncio.run(restarted.http.close())
    restarted.database.close()


def test_concurrent_auto_season_enables_cannot_replace_the_active_delay(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))

    async def exercise() -> None:
        results = await asyncio.gather(
            orchestrator.configure_auto_new_season(True, 4),
            orchestrator.configure_auto_new_season(True, 2),
            return_exceptions=True,
        )
        successful = [result for result in results if isinstance(result, dict)]
        rejected = [result for result in results if isinstance(result, ValueError)]
        assert len(successful) == 1
        assert len(rejected) == 1
        assert "turn automatic seasons off" in str(rejected[0])
        assert orchestrator.auto_new_season_enabled is True
        assert orchestrator.auto_new_season_grace_seconds in {2 * 60 * 60, 4 * 60 * 60}
        await orchestrator.http.close()

    try:
        asyncio.run(exercise())
    finally:
        orchestrator.database.close()


def test_manual_reset_is_single_flight_and_blocks_automatic_rollover(
    tmp_path: Path,
) -> None:
    orchestrator = Orchestrator(Settings(data_dir=tmp_path, demo_mode=True, _env_file=None))

    async def exercise() -> None:
        await orchestrator.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000)
        orchestrator.running = True
        orchestrator.auto_new_season_enabled = True
        first = await orchestrator.begin_reset_portfolio()
        duplicate = await orchestrator.begin_reset_portfolio()
        assert duplicate["operation_id"] == first["operation_id"]
        portfolio = orchestrator.broker.snapshot(RiskMode.BALANCED, persist_peak=False)
        state, _, eligible = orchestrator._auto_new_season_gate(  # noqa: SLF001
            portfolio,
            datetime.now(UTC),
        )
        assert state == "operation_pending"
        assert eligible is False
        assert orchestrator._season_operation_task is not None  # noqa: SLF001
        await asyncio.wait_for(orchestrator._season_operation_task, timeout=3)  # noqa: SLF001
        assert orchestrator.season_operation_status()["state"] == "completed"
        assert orchestrator.broker.initialized is False
        await orchestrator.http.close()

    try:
        asyncio.run(exercise())
    finally:
        orchestrator.database.close()


def test_interrupted_reset_reconciles_from_the_committed_ledger(tmp_path: Path) -> None:
    now = datetime.now(UTC).isoformat()
    operation = {
        "operation_id": "interrupted-reset",
        "kind": "reset",
        "state": "running",
        "stage": "archiving_season",
        "detail": "Resetting",
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
    }

    incomplete_dir = tmp_path / "incomplete"
    incomplete = Database(incomplete_dir / "signal_arcade.sqlite3")
    incomplete.initialize_portfolio("season-one", 1_000_000_000, "SOL")
    incomplete.set_setting("season_operation", operation)
    incomplete.close()
    retained = Orchestrator(Settings(data_dir=incomplete_dir, demo_mode=True, _env_file=None))
    assert retained.season_operation_status()["state"] == "failed"
    assert retained.broker.initialized is True
    asyncio.run(retained.http.close())
    retained.database.close()

    completed_dir = tmp_path / "completed"
    completed = Database(completed_dir / "signal_arcade.sqlite3")
    completed.set_setting("season_operation", operation)
    completed.close()
    archived = Orchestrator(Settings(data_dir=completed_dir, demo_mode=True, _env_file=None))
    assert archived.season_operation_status()["state"] == "completed"
    assert archived.broker.initialized is False
    asyncio.run(archived.http.close())
    archived.database.close()
