from __future__ import annotations

from datetime import UTC, datetime, timedelta

from signal_arcade.models import RISK_LIMITS, DataValue, FeatureSnapshot, Position, RiskMode
from signal_arcade.paper.exit_policy import assess_exit


def _value(value: float, now: datetime) -> DataValue:
    return DataValue(
        value=value,
        unit="fraction",
        as_of=now,
        sources=["test"],
        freshness_seconds=0,
        quality=1,
    )


def features(
    now: datetime,
    *,
    strong: bool = True,
    progress: float = 0.5,
    hard_flags: list[str] | None = None,
) -> FeatureSnapshot:
    values = {
        "curve_progress": _value(progress, now),
        "buy_ratio_5m": _value(0.72 if strong else 0.38, now),
        "momentum_1m": _value(0.18 if strong else -0.16, now),
        "unique_wallets_5m": _value(18 if strong else 4, now),
        "trade_count_1m": _value(22 if strong else 3, now),
        "drawdown_5m": _value(0.04 if strong else 0.24, now),
        "wallet_volume_hhi": _value(0.12 if strong else 0.52, now),
    }
    return FeatureSnapshot(
        mint="mint",
        symbol="TEST",
        name="Test",
        venue="pump_curve",
        computed_at=now,
        values=values,
        data_confidence=0.9,
        hard_flags=hard_flags or [],
    )


def position(
    now: datetime,
    *,
    age_seconds: int,
    mark: int = 110,
    peak: int = 110,
) -> Position:
    return Position(
        position_id="position",
        mint="mint",
        symbol="TEST",
        token_units=1,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=now - timedelta(seconds=age_seconds),
        entry_fill_id="fill",
        last_mark_lamports=mark,
        unrealized_pnl_lamports=mark - 100,
        last_marked_at=now,
        mark_is_stale=False,
        risk_mode_at_entry=RiskMode.BALANCED,
        peak_mark_lamports=peak,
        peak_marked_at=now,
    )


def test_strong_evidence_extends_soft_hold_but_never_absolute_ceiling() -> None:
    now = datetime.now(UTC)
    limits = RISK_LIMITS[RiskMode.BALANCED]

    extended = assess_exit(
        position=position(now, age_seconds=limits.max_hold_seconds + 1),
        features=features(now),
        now=now,
        limits=limits,
    )
    absolute = assess_exit(
        position=position(now, age_seconds=limits.hard_max_hold_seconds + 1),
        features=features(now),
        now=now,
        limits=limits,
    )

    assert extended.action == "hold"
    assert extended.reason == "adaptive_extension"
    assert extended.support_score >= limits.minimum_hold_support
    assert absolute.action == "exit"
    assert absolute.reason == "absolute_time_exit"


def test_learned_review_can_move_earlier_but_cannot_postpone_mode_review() -> None:
    now = datetime.now(UTC)
    limits = RISK_LIMITS[RiskMode.SAFE]
    incomplete = features(now).model_copy(update={"values": {"curve_progress": _value(0.5, now)}})

    assessment = assess_exit(
        position=position(now, age_seconds=limits.max_hold_seconds + 1),
        features=incomplete,
        now=now,
        limits=limits,
        soft_hold_seconds=limits.hard_max_hold_seconds,
    )

    assert assessment.soft_hold_seconds == limits.max_hold_seconds
    assert (assessment.action, assessment.reason) == ("exit", "time_exit")


def test_profitable_position_uses_trailing_guard_instead_of_fixed_ceiling() -> None:
    now = datetime.now(UTC)
    limits = RISK_LIMITS[RiskMode.BALANCED]
    still_running = assess_exit(
        position=position(now, age_seconds=120, mark=140, peak=150),
        features=features(now),
        now=now,
        limits=limits,
    )
    retraced = assess_exit(
        position=position(now, age_seconds=121, mark=130, peak=150),
        features=features(now),
        now=now,
        limits=limits,
    )

    assert still_running.action == "hold"
    assert still_running.reason == "protecting_winner"
    assert retraced.action == "exit"
    assert retraced.reason == "trailing_profit"


def test_route_and_migration_edges_never_invent_an_exit() -> None:
    now = datetime.now(UTC)
    limits = RISK_LIMITS[RiskMode.BALANCED]
    near_migration = assess_exit(
        position=position(now, age_seconds=60),
        features=features(now, progress=limits.migration_guard_progress),
        now=now,
        limits=limits,
    )
    route_missing = assess_exit(
        position=position(now, age_seconds=limits.hard_max_hold_seconds + 1, mark=20),
        features=features(now, hard_flags=["curve_complete_route_unconfirmed"]),
        now=now,
        limits=limits,
    )
    stale_loss = assess_exit(
        position=position(now, age_seconds=60, mark=20),
        features=features(now, hard_flags=["stale_market_data"]),
        now=now,
        limits=limits,
    )

    assert (near_migration.action, near_migration.reason) == (
        "exit",
        "migration_route_guard",
    )
    assert (route_missing.action, route_missing.reason) == (
        "wait",
        "exit_route_unavailable",
    )
    assert (stale_loss.action, stale_loss.reason) == ("wait", "waiting_for_fresh_market")


def test_deteriorating_market_and_failed_mint_safety_exit_early() -> None:
    now = datetime.now(UTC)
    limits = RISK_LIMITS[RiskMode.BALANCED]
    deteriorating = assess_exit(
        position=position(now, age_seconds=45, mark=95, peak=105),
        features=features(now, strong=False),
        now=now,
        limits=limits,
    )
    unsafe = assess_exit(
        position=position(now, age_seconds=10),
        features=features(now, hard_flags=["mint_account_failed_safety_checks"]),
        now=now,
        limits=limits,
    )

    assert (deteriorating.action, deteriorating.reason) == (
        "exit",
        "signal_deterioration",
    )
    assert (unsafe.action, unsafe.reason) == ("exit", "mint_safety_exit")
