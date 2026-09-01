from __future__ import annotations

from datetime import datetime

from ..models import ExitAction, ExitAssessment, FeatureSnapshot, Position, RiskLimits
from ..strategy import BASELINE_VERSION

POLICY_VERSION = "adaptive-exit-v1"
ROUTE_BLOCKERS = {
    "missing_curve_reserves",
    "stale_market_data",
    "curve_complete_route_unconfirmed",
    "pumpswap_route_unverified",
    "unsupported_quote_mint_v1",
    "unsupported_token_program",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _available_number(features: FeatureSnapshot, key: str) -> float | None:
    item = features.values.get(key)
    if item is None or item.value is None or isinstance(item.value, bool) or item.quality <= 0:
        return None
    try:
        return float(item.value)
    except (TypeError, ValueError):
        return None


def hold_support(
    features: FeatureSnapshot,
    *,
    baseline_version: str | None = None,
) -> tuple[float, list[str], int]:
    """Return transparent continuation support from fresh, observable evidence only."""

    buy_ratio = _available_number(features, "buy_ratio_5m")
    momentum = _available_number(features, "momentum_1m")
    wallets = _available_number(features, "unique_wallets_5m")
    trades = _available_number(features, "trade_count_1m")
    drawdown = _available_number(features, "drawdown_5m")
    concentration = _available_number(features, "wallet_volume_hhi")
    economic_credit = 1.0
    if baseline_version == BASELINE_VERSION:
        meaningful_volume = _available_number(features, "meaningful_volume_ratio")
        meaningful_wallets = _available_number(features, "meaningful_wallet_ratio")
        economic_credit = _clamp(
            min(
                meaningful_volume if meaningful_volume is not None else 0.0,
                meaningful_wallets if meaningful_wallets is not None else 0.0,
            )
            / 0.60
        )

    components = {
        "buy": (
            0.0
            if buy_ratio is None
            else _clamp((buy_ratio - 0.35) / 0.35) * economic_credit
        ),
        "momentum": (
            0.0
            if momentum is None
            else _clamp((momentum + 0.10) / 0.45) * economic_credit
        ),
        "wallets": 0.0 if wallets is None else _clamp(wallets / 20) * economic_credit,
        "trades": 0.0 if trades is None else _clamp(trades / 20) * economic_credit,
        "drawdown": 0.0 if drawdown is None else 1 - _clamp(drawdown / 0.35),
        "concentration": (
            0.0 if concentration is None else 1 - _clamp((concentration - 0.08) / 0.42)
        ),
        "confidence": features.data_confidence,
    }
    score = _clamp(
        0.22 * components["buy"]
        + 0.18 * components["momentum"]
        + 0.14 * components["wallets"]
        + 0.12 * components["trades"]
        + 0.14 * components["drawdown"]
        + 0.10 * components["concentration"]
        + 0.10 * components["confidence"]
    )
    evidence: list[str] = []
    if buy_ratio is not None:
        evidence.append(f"5m buy ratio {buy_ratio:.0%}")
    if momentum is not None:
        evidence.append(f"1m momentum {momentum:+.1%}")
    if drawdown is not None:
        evidence.append(f"5m drawdown {drawdown:.1%}")
    if wallets is not None:
        evidence.append(f"{int(wallets)} unique wallets in 5m")
    if baseline_version == BASELINE_VERSION:
        evidence.append(f"economically meaningful activity credit {economic_credit:.0%}")
    available = sum(
        value is not None
        for value in (buy_ratio, momentum, wallets, trades, drawdown, concentration)
    )
    return score, evidence[:5], available


def assess_exit(
    *,
    position: Position,
    features: FeatureSnapshot,
    now: datetime,
    limits: RiskLimits,
    soft_hold_seconds: int | None = None,
    persistent_integrity_reason: str | None = None,
) -> ExitAssessment:
    """Evaluate one open position without inventing a price or bypassing route safety."""

    # Learning may bring the normal review forward, but cannot postpone the mode/entry
    # review point. Strong current evidence—not a historical model—earns any extension.
    soft_hold = max(30, min(soft_hold_seconds or limits.max_hold_seconds, limits.max_hold_seconds))
    hard_hold = limits.hard_max_hold_seconds
    age = max(0.0, (now - position.opened_at).total_seconds())
    pnl = (
        position.unrealized_pnl_lamports / position.entry_cost_lamports
        if position.entry_cost_lamports
        else -1.0
    )
    peak_mark = max(position.last_mark_lamports, position.peak_mark_lamports)
    peak_return = (
        peak_mark / position.entry_cost_lamports - 1 if position.entry_cost_lamports else -1.0
    )
    peak_drawdown = 0.0 if peak_mark <= 0 else _clamp(1 - position.last_mark_lamports / peak_mark)
    support, evidence, available_signals = hold_support(
        features,
        baseline_version=position.baseline_version_at_entry,
    )

    def result(action: str, reason: str, extra: str | None = None) -> ExitAssessment:
        details = [*evidence]
        if extra:
            details.insert(0, extra)
        return ExitAssessment(
            policy_version=POLICY_VERSION,
            evaluated_at=now,
            action=ExitAction(action),
            reason=reason,
            support_score=support,
            pnl_fraction=max(-1.0, min(10.0, pnl)),
            peak_return_fraction=max(-1.0, min(10.0, peak_return)),
            drawdown_from_peak_fraction=peak_drawdown,
            age_seconds=age,
            soft_hold_seconds=soft_hold,
            hard_hold_seconds=hard_hold,
            evidence=details[:5],
        )

    route_blockers = ROUTE_BLOCKERS.intersection(features.hard_flags)
    if route_blockers:
        reason = (
            "waiting_for_fresh_market"
            if "stale_market_data" in route_blockers
            else "exit_route_unavailable"
        )
        return result("wait", reason, ", ".join(sorted(route_blockers)))

    if "creator_sold_recently" in features.hard_flags:
        return result("exit", "creator_sell_exit")
    if "mint_account_failed_safety_checks" in features.hard_flags:
        return result("exit", "mint_safety_exit")
    if pnl <= -limits.stop_loss_fraction:
        return result("exit", "stop_loss")

    progress = _available_number(features, "curve_progress")
    if (
        features.venue == "pump_curve"
        and progress is not None
        and progress >= limits.migration_guard_progress
    ):
        return result(
            "exit",
            "migration_route_guard",
            f"Curve progress {progress:.1%} is near the unconfirmed migration boundary",
        )

    if persistent_integrity_reason is not None:
        return result(
            "exit",
            persistent_integrity_reason,
            "Manipulation evidence persisted across time-separated checkpoints",
        )

    if (
        peak_return >= limits.take_profit_fraction
        and peak_drawdown >= limits.trailing_stop_fraction
    ):
        return result("exit", "trailing_profit")
    if age >= hard_hold:
        return result("exit", "absolute_time_exit")

    buy_ratio = _available_number(features, "buy_ratio_5m")
    momentum = _available_number(features, "momentum_1m")
    drawdown = _available_number(features, "drawdown_5m")
    concentration = _available_number(features, "wallet_volume_hhi")
    collapse_signals = sum(
        (
            buy_ratio is not None and buy_ratio < 0.42,
            momentum is not None and momentum <= -0.10,
            drawdown is not None and drawdown >= 0.18,
            concentration is not None and concentration >= 0.45,
        )
    )
    if age >= 30 and features.data_confidence >= 0.5 and collapse_signals >= 2:
        return result("exit", "signal_deterioration")

    # A profit target starts protection; it is not an automatic ceiling. Continue only
    # when a complete evidence set still clears the configured support threshold.
    evidence_complete = available_signals >= 4
    if pnl >= limits.take_profit_fraction and (
        not evidence_complete or support < limits.minimum_hold_support
    ):
        return result("exit", "take_profit")
    if age >= soft_hold and (not evidence_complete or support < limits.minimum_hold_support):
        return result("exit", "time_exit")
    if age >= soft_hold:
        return result("hold", "adaptive_extension")
    if peak_return >= limits.take_profit_fraction:
        return result("hold", "protecting_winner")
    return result("hold", "evidence_supports_hold")
