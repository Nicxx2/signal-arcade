from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from signal_arcade.models import (
    RISK_LIMITS,
    OrderStatus,
    PaperOrder,
    Position,
    ProfileTransitionStrategy,
    QuoteCurrency,
    RiskMode,
    Side,
)
from signal_arcade.orchestrator import (
    PROFILE_TRANSITION_MANUAL_SETTLEMENT_SECONDS,
    Orchestrator,
)
from signal_arcade.risk_profiles import DrawdownPolicy, DrawdownPolicyKind


def close_orchestrator(orchestrator: Orchestrator) -> None:
    asyncio.run(orchestrator.http.close())
    orchestrator.database.close()


def prepare_locked_orchestrator(settings) -> Orchestrator:  # type: ignore[no-untyped-def]
    orchestrator = Orchestrator(settings)
    asyncio.run(orchestrator.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000))
    asyncio.run(orchestrator.resume_trading())
    return orchestrator


def test_unstarted_profile_changes_in_place_without_archiving(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = Orchestrator(settings)
    asyncio.run(orchestrator.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000))

    result = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))

    assert result["transition_required"] is False
    assert orchestrator.risk_mode == RiskMode.SAFE
    assert orchestrator.broker.season_profile is not None
    assert orchestrator.broker.season_profile["risk_mode"] == "safe"
    assert orchestrator.broker.season_profile["locked_at"] is None
    assert len(orchestrator.database.list_paper_seasons()) == 1
    close_orchestrator(orchestrator)


def test_locked_profile_transition_is_atomic_and_restores_running_state(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    source_season = orchestrator.broker.season_id

    requested = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    completed = asyncio.run(orchestrator._profile_transition_tick(datetime.now(UTC)))  # noqa: SLF001

    assert requested["state"] == "running"
    assert completed is not None
    assert orchestrator.season_operation_status()["state"] == "completed"
    assert orchestrator.broker.season_id != source_season
    assert orchestrator.risk_mode == RiskMode.SAFE
    assert orchestrator.running is True
    seasons = orchestrator.database.list_paper_seasons()
    assert [(season["status"], season["terminal_reason"]) for season in seasons] == [
        ("completed", "profile_change_safe"),
        ("current", None),
    ]
    assert seasons[1]["profile"]["risk_mode"] == "safe"
    assert seasons[1]["profile"]["locked_at"] is not None
    close_orchestrator(orchestrator)


def test_transition_cancels_buys_but_preserves_exits_across_restart(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    now = datetime.now(UTC)
    buy = PaperOrder(
        order_id="buy",
        mint="buy-mint",
        symbol="BUY",
        side=Side.BUY,
        requested_sol_lamports=1,
        fill_after=now,
    )
    sell = PaperOrder(
        order_id="sell",
        mint="sell-mint",
        symbol="SELL",
        side=Side.SELL,
        requested_token_units=1,
        fill_after=now,
    )
    for order in (buy, sell):
        orchestrator.broker.pending[order.order_id] = order
        orchestrator.database.save_order(order)

    asyncio.run(orchestrator.request_risk_mode(RiskMode.AGGRESSIVE))

    assert set(orchestrator.broker.pending) == {"sell"}
    cancelled = orchestrator.database.list_orders([OrderStatus.CANCELLED.value])
    assert [order.order_id for order in cancelled] == ["buy"]
    interrupted_buy = PaperOrder(
        order_id="buy-at-crash-boundary",
        mint="late-buy-mint",
        symbol="LATE",
        side=Side.BUY,
        requested_sol_lamports=1,
        fill_after=now,
    )
    orchestrator.broker.pending[interrupted_buy.order_id] = interrupted_buy
    orchestrator.database.save_order(interrupted_buy)
    close_orchestrator(orchestrator)

    restarted = Orchestrator(settings)
    assert restarted._profile_transition_active() is True  # noqa: SLF001
    assert set(restarted.broker.pending) == {"sell"}
    assert restarted.running is False
    assert {
        order.order_id for order in restarted.database.list_orders([OrderStatus.CANCELLED.value])
    } == {"buy", "buy-at-crash-boundary"}
    assert restarted.season_operation_status()["cancelled_pending_buys"] == 2
    close_orchestrator(restarted)


def test_transition_heartbeat_never_executes_a_late_pending_buy(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    now = datetime.now(UTC)
    late_buy = PaperOrder(
        order_id="late-buy",
        mint="late-buy-mint",
        symbol="LATE",
        side=Side.BUY,
        requested_sol_lamports=1,
        fill_after=now - timedelta(seconds=1),
    )
    orchestrator.broker.pending[late_buy.order_id] = late_buy
    orchestrator.database.save_order(late_buy)

    receipts, _, _, _ = orchestrator._heartbeat_tick(now)  # noqa: SLF001

    assert receipts == []
    assert "late-buy" not in orchestrator.broker.pending
    saved = orchestrator.database.list_orders([OrderStatus.CANCELLED.value])
    assert any(order.order_id == "late-buy" for order in saved)
    close_orchestrator(orchestrator)


def test_transition_requests_are_idempotent_but_cannot_be_retargeted(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)

    first = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    repeated = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))

    assert repeated["operation_id"] == first["operation_id"]
    try:
        asyncio.run(orchestrator.request_risk_mode(RiskMode.AGGRESSIVE))
    except ValueError as exc:
        assert "wait for the current season operation" in str(exc)
    else:
        raise AssertionError("a running transition was unexpectedly retargeted")
    close_orchestrator(orchestrator)


def test_stopped_transition_creates_an_unlocked_stopped_season(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    asyncio.run(orchestrator.pause_trading())

    asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    asyncio.run(orchestrator._profile_transition_tick(datetime.now(UTC)))  # noqa: SLF001

    assert orchestrator.running is False
    assert orchestrator.broker.season_profile is not None
    assert orchestrator.broker.season_profile["locked_at"] is None
    assert orchestrator.database.get_setting("trading_enabled") is False
    close_orchestrator(orchestrator)


def test_dormant_transition_waits_full_healthy_grace_and_revival_resets_it(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    started = datetime.now(UTC)
    position = Position(
        position_id="dormant",
        mint="dormant",
        symbol="DORMANT",
        token_units=1,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=started - timedelta(days=2),
        entry_fill_id="fill",
        last_mark_lamports=1,
        last_marked_at=started - timedelta(days=1),
        mark_is_stale=True,
        mark_is_executable=False,
        risk_mode_at_entry=RiskMode.BALANCED,
    )
    orchestrator.broker.positions[position.mint] = position
    orchestrator.database.save_position(position)
    orchestrator.auto_new_season_grace_seconds = 10
    asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))

    assert asyncio.run(orchestrator._profile_transition_tick(started)) is None  # noqa: SLF001
    assert orchestrator.season_operation_status()["stage"] == "waiting_for_dormant_recovery"

    position.last_marked_at = started + timedelta(seconds=5)
    position.mark_is_stale = False
    position.mark_is_executable = True
    orchestrator.database.save_position(position)
    assert (
        asyncio.run(
            orchestrator._profile_transition_tick(started + timedelta(seconds=5))  # noqa: SLF001
        )
        is None
    )
    operation = orchestrator.season_operation_status()
    assert operation["stage"] == "draining_positions"
    assert operation["dormant_eligible_since"] is None
    close_orchestrator(orchestrator)


def test_exact_profile_uses_frozen_limits_after_code_defaults_change(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    orchestrator = Orchestrator(settings)
    asyncio.run(orchestrator.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000))
    frozen = orchestrator.broker.risk_limits(RiskMode.BALANCED)
    monkeypatch.setitem(
        RISK_LIMITS,
        RiskMode.BALANCED,
        frozen.model_copy(update={"max_open_positions": 99}),
    )

    assert orchestrator.broker.risk_limits(RiskMode.BALANCED).max_open_positions == 4
    close_orchestrator(orchestrator)


def test_drawdown_only_change_uses_new_season_but_preserves_learning_lineage(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    source_profile = dict(orchestrator.broker.season_profile or {})

    requested = asyncio.run(
        orchestrator.request_season_profile(
            RiskMode.BALANCED,
            DrawdownPolicy(kind=DrawdownPolicyKind.DISABLED),
        )
    )
    asyncio.run(orchestrator._profile_transition_tick(datetime.now(UTC)))  # noqa: SLF001

    target_profile = orchestrator.broker.season_profile
    assert requested["target_profile"]["effective_drawdown_bps"] is None
    assert target_profile is not None
    assert target_profile["profile_fingerprint"] != source_profile["profile_fingerprint"]
    assert target_profile["learning_fingerprint"] == source_profile["learning_fingerprint"]
    assert orchestrator.broker.drawdown_limit_fraction() is None
    assert orchestrator.broker.risk_limits().stop_loss_fraction == 0.12
    close_orchestrator(orchestrator)


def test_end_now_records_untradeable_inventory_without_fabricating_a_fill(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    started = datetime.now(UTC)
    position = Position(
        position_id="unresolved-position",
        mint="unresolved-mint",
        symbol="REAL",
        token_units=123,
        entry_cost_lamports=1_000,
        book_value_lamports=985,
        opened_at=started - timedelta(hours=2),
        entry_fill_id="real-entry-fill",
        last_mark_lamports=450,
        last_marked_at=started - timedelta(hours=1),
        mark_is_stale=True,
        mark_is_executable=False,
        mark_blockers=["stale_market_data"],
        risk_mode_at_entry=RiskMode.BALANCED,
    )
    orchestrator.broker.positions[position.mint] = position
    orchestrator.database.save_position(position)

    requested = asyncio.run(
        orchestrator.request_season_profile(
            RiskMode.SAFE,
            DrawdownPolicy(),
            transition_strategy=ProfileTransitionStrategy.END_NOW,
        )
    )
    manual_started_at = datetime.fromisoformat(str(requested["manual_settlement_started_at"]))
    deadline = datetime.fromisoformat(str(requested["manual_settlement_deadline"]))
    assert (
        asyncio.run(orchestrator._profile_transition_tick(manual_started_at))  # noqa: SLF001
        is None
    )
    assert orchestrator.season_operation_status()["stage"] == "settling_manual_exits"

    completed = asyncio.run(
        orchestrator._profile_transition_tick(deadline + timedelta(seconds=1))  # noqa: SLF001
    )
    assert completed is not None
    seasons = orchestrator.database.list_paper_seasons()
    archived = seasons[0]
    assert archived["terminal_reason"] == "profile_change_manual"
    assert archived["result_quality"] == "unresolved"
    assert archived["comparable"] is False
    assert archived["open_positions"] == 1
    assert archived["unresolved_inventory"] == [
        {
            "book_value_minor": 985,
            "entry_cost_minor": 1_000,
            "last_known_mark_minor": 450,
            "last_marked_at": position.last_marked_at.isoformat(),
            "mark_blockers": ["stale_market_data"],
            "market_status": "dormant",
            "mint": "unresolved-mint",
            "position_id": "unresolved-position",
            "quote_currency": "SOL",
            "quote_decimals": 9,
            "recorded_at": (deadline + timedelta(seconds=1)).isoformat(),
            "retired_at": (deadline + timedelta(seconds=1)).isoformat(),
            "retirement_reason": "profile_change_manual",
            "season_id": archived["season_id"],
            "symbol": "REAL",
            "token_units": 123,
            "was_executed": False,
        }
    ]
    assert orchestrator.database.list_fills() == []
    assert orchestrator.broker.positions == {}
    close_orchestrator(orchestrator)


def test_end_now_schedules_real_exits_then_honours_the_bounded_deadline(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    started = datetime.now(UTC)
    position = Position(
        position_id="executable-position",
        mint="executable-mint",
        symbol="EXIT",
        token_units=50,
        entry_cost_lamports=500,
        book_value_lamports=485,
        opened_at=started - timedelta(minutes=5),
        entry_fill_id="entry-fill",
        last_mark_lamports=550,
        last_marked_at=started,
        mark_is_stale=False,
        mark_is_executable=True,
        risk_mode_at_entry=RiskMode.BALANCED,
    )
    orchestrator.broker.positions[position.mint] = position
    orchestrator.database.save_position(position)
    requested = asyncio.run(
        orchestrator.request_season_profile(
            RiskMode.AGGRESSIVE,
            DrawdownPolicy(),
            transition_strategy=ProfileTransitionStrategy.END_NOW,
        )
    )

    manual_started_at = datetime.fromisoformat(str(requested["manual_settlement_started_at"]))
    assert (
        asyncio.run(orchestrator._profile_transition_tick(manual_started_at))  # noqa: SLF001
        is None
    )
    pending = list(orchestrator.broker.pending.values())
    assert len(pending) == 1
    assert pending[0].side == Side.SELL
    assert pending[0].failure_reason == "scheduled_reason:manual_profile_change"
    assert orchestrator.database.list_fills() == []

    deadline = datetime.fromisoformat(
        str(orchestrator.season_operation_status()["manual_settlement_deadline"])
    )
    assert orchestrator._profile_transition_exit_management_active(  # noqa: SLF001
        deadline - timedelta(microseconds=1)
    )
    assert not orchestrator._profile_transition_exit_management_active(deadline)  # noqa: SLF001
    assert (
        asyncio.run(
            orchestrator._profile_transition_tick(deadline + timedelta(seconds=1))  # noqa: SLF001
        )
        is not None
    )
    assert orchestrator.season_operation_status()["cancelled_manual_exits"] == 1
    assert orchestrator.database.list_fills() == []
    assert orchestrator.database.list_paper_seasons()[0]["comparable"] is False
    close_orchestrator(orchestrator)


def test_corrupt_future_manual_timestamps_cannot_expand_the_exit_window(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    requested = asyncio.run(
        orchestrator.request_season_profile(
            RiskMode.SAFE,
            DrawdownPolicy(),
            transition_strategy=ProfileTransitionStrategy.END_NOW,
        )
    )
    now = datetime.now(UTC)
    corrupted = {
        **requested,
        "manual_settlement_started_at": (now + timedelta(days=1)).isoformat(),
        "manual_settlement_deadline": (now + timedelta(days=2)).isoformat(),
    }

    deadline = orchestrator._manual_profile_settlement_deadline(corrupted, now)  # noqa: SLF001

    assert now < deadline <= now + timedelta(seconds=PROFILE_TRANSITION_MANUAL_SETTLEMENT_SECONDS)
    close_orchestrator(orchestrator)


def test_safe_transition_can_only_be_escalated_to_end_now_for_the_same_target(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    first = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    old_started_at = datetime.now(UTC) - timedelta(minutes=5)
    aged = {**first, "started_at": old_started_at.isoformat()}
    orchestrator._season_operation = aged  # noqa: SLF001 - simulate a long safe drain
    orchestrator.database.set_setting("season_operation", aged)
    escalated = asyncio.run(
        orchestrator.request_season_profile(
            RiskMode.SAFE,
            DrawdownPolicy(),
            transition_strategy=ProfileTransitionStrategy.END_NOW,
        )
    )

    assert escalated["operation_id"] == first["operation_id"]
    assert escalated["transition_strategy"] == "end_now"
    manual_started_at = datetime.fromisoformat(str(escalated["manual_settlement_started_at"]))
    manual_deadline = datetime.fromisoformat(str(escalated["manual_settlement_deadline"]))
    assert manual_started_at > old_started_at + timedelta(minutes=4)
    assert manual_deadline - manual_started_at == timedelta(
        seconds=PROFILE_TRANSITION_MANUAL_SETTLEMENT_SECONDS
    )
    repeated_safe = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    assert repeated_safe["transition_strategy"] == "end_now"
    close_orchestrator(orchestrator)


def test_end_now_escalation_cannot_race_a_safe_transition_commit(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)

    async def race_commit() -> dict[str, object]:
        await orchestrator.request_risk_mode(RiskMode.SAFE)
        async with orchestrator._event_lock:  # noqa: SLF001 - reproduce heartbeat boundary
            escalation = asyncio.create_task(
                orchestrator.request_season_profile(
                    RiskMode.SAFE,
                    DrawdownPolicy(),
                    transition_strategy=ProfileTransitionStrategy.END_NOW,
                )
            )
            await asyncio.sleep(0)
            completed = await orchestrator._profile_transition_tick(  # noqa: SLF001
                datetime.now(UTC)
            )
            assert completed is not None
        return await escalation

    response = asyncio.run(race_commit())

    assert response == {
        "kind": "profile_preference",
        "state": "completed",
        "mode": "safe",
        "transition_required": False,
    }
    assert orchestrator.database.list_paper_seasons()[0]["terminal_reason"] == (
        "profile_change_safe"
    )
    assert orchestrator.database.list_paper_seasons()[0]["comparable"] is True
    close_orchestrator(orchestrator)


def test_manually_ended_season_is_visible_but_excluded_from_result_comparisons(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    asyncio.run(
        orchestrator.request_season_profile(
            RiskMode.SAFE,
            DrawdownPolicy(),
            transition_strategy=ProfileTransitionStrategy.END_NOW,
        )
    )
    asyncio.run(orchestrator._profile_transition_tick(datetime.now(UTC)))  # noqa: SLF001

    results = asyncio.run(orchestrator.seasons_view())
    assert results["summary"]["completed_seasons"] == 1
    assert results["summary"]["comparable_seasons"] == 0
    assert results["summary"]["profitable_seasons"] == 0
    assert results["summary"]["losing_seasons"] == 0
    assert results["summary"]["average_win_rate"] is None
    assert results["summary"]["best_return_fraction"] is None
    assert results["seasons"][0]["terminal_reason"] == "profile_change_manual"
    close_orchestrator(orchestrator)


def test_end_now_deadline_and_unresolved_audit_survive_restart(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    now = datetime.now(UTC)
    position = Position(
        position_id="restart-position",
        mint="restart-mint",
        symbol="WAIT",
        token_units=7,
        entry_cost_lamports=70,
        book_value_lamports=65,
        opened_at=now - timedelta(minutes=10),
        entry_fill_id="restart-fill",
        mark_is_stale=True,
        mark_is_executable=False,
    )
    orchestrator.broker.positions[position.mint] = position
    orchestrator.database.save_position(position)
    requested = asyncio.run(
        orchestrator.request_season_profile(
            RiskMode.SAFE,
            DrawdownPolicy(),
            transition_strategy=ProfileTransitionStrategy.END_NOW,
        )
    )
    deadline = datetime.fromisoformat(str(requested["manual_settlement_deadline"]))
    operation_id = requested["operation_id"]
    close_orchestrator(orchestrator)

    restarted = Orchestrator(settings)
    recovered = restarted.season_operation_status()
    assert recovered["operation_id"] == operation_id
    assert recovered["transition_strategy"] == "end_now"
    assert recovered["manual_settlement_started_at"] == requested["manual_settlement_started_at"]
    assert recovered["manual_settlement_deadline"] == deadline.isoformat()
    assert (
        asyncio.run(
            restarted._profile_transition_tick(deadline + timedelta(seconds=1))  # noqa: SLF001
        )
        is not None
    )
    archived = restarted.database.list_paper_seasons()[0]
    assert archived["unresolved_inventory"][0]["mint"] == "restart-mint"
    close_orchestrator(restarted)


def test_unknown_stored_transition_strategy_fails_closed_to_safe_drain(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    requested = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    corrupted = {**requested, "transition_strategy": "unknown-future-strategy"}
    orchestrator._season_operation = corrupted  # noqa: SLF001
    orchestrator.database.set_setting("season_operation", corrupted)

    assert (
        asyncio.run(orchestrator._profile_transition_tick(datetime.now(UTC)))  # noqa: SLF001
        is not None
    )
    archived = orchestrator.database.list_paper_seasons()[0]
    assert archived["terminal_reason"] == "profile_change_safe"
    assert archived["comparable"] is True
    close_orchestrator(orchestrator)


def test_stale_transition_cannot_roll_over_a_different_current_season(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    requested = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    stale = {**requested, "source_season_id": "another-season"}
    orchestrator._season_operation = stale  # noqa: SLF001 - persisted-state fault injection
    orchestrator.database.set_setting("season_operation", stale)
    original_season_id = orchestrator.broker.season_id

    assert (
        asyncio.run(orchestrator._profile_transition_tick(datetime.now(UTC)))  # noqa: SLF001
        is None
    )

    assert orchestrator.season_operation_status()["state"] == "failed"
    assert orchestrator.broker.season_id == original_season_id
    assert [
        (season["season_id"], season["status"])
        for season in orchestrator.database.list_paper_seasons()
    ] == [(original_season_id, "current")]
    close_orchestrator(orchestrator)


def test_malformed_saved_target_profile_fails_without_archiving(settings) -> None:  # type: ignore[no-untyped-def]
    orchestrator = prepare_locked_orchestrator(settings)
    requested = asyncio.run(orchestrator.request_risk_mode(RiskMode.SAFE))
    target = {**requested["target_profile"], "risk_limits": {}}
    malformed = {**requested, "target_profile": target}
    orchestrator._season_operation = malformed  # noqa: SLF001 - persisted-state fault injection
    orchestrator.database.set_setting("season_operation", malformed)
    original_season_id = orchestrator.broker.season_id

    assert (
        asyncio.run(orchestrator._profile_transition_tick(datetime.now(UTC)))  # noqa: SLF001
        is None
    )

    assert orchestrator.season_operation_status()["state"] == "failed"
    assert orchestrator.broker.season_id == original_season_id
    assert orchestrator.database.list_paper_seasons()[0]["status"] == "current"
    close_orchestrator(orchestrator)
