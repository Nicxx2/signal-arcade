from __future__ import annotations

import uuid

from ..models import (
    RISK_LIMITS,
    Decision,
    DecisionAction,
    DecisionScore,
    FeatureSnapshot,
    RiskLimits,
    RiskMode,
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class DecisionEngine:
    """Transparent V1 baseline. It abstains when evidence is unreliable."""

    version = "baseline-v1.1"

    def __init__(
        self,
        *,
        default_fee_bps: int = 125,
        one_way_network_fee_lamports: int = 30_000,
    ) -> None:
        self.default_fee_bps = default_fee_bps
        self.one_way_network_fee_lamports = one_way_network_fee_lamports

    def evaluate(
        self,
        features: FeatureSnapshot,
        mode: RiskMode,
        *,
        planned_order_size_sol: float | None = None,
        policy_limits: RiskLimits | None = None,
    ) -> Decision:
        limits = policy_limits or RISK_LIMITS[mode]
        age = features.number("age_seconds")
        trades = features.number("trade_count_5m")
        trade_rate = features.number("trade_count_1m")
        unique = features.number("unique_wallets_5m")
        buy_ratio = features.number("buy_ratio_5m")
        progress = features.number("curve_progress")
        momentum = features.number("momentum_1m")
        drawdown = features.number("drawdown_5m")
        hhi = features.number("wallet_volume_hhi", 1.0)
        repeated = features.number("repeated_amount_ratio")
        same_slot = features.number("same_slot_ratio")
        creator_sells = features.number("creator_sells_5m")
        reserve_sol = features.number("virtual_quote_reserve_sol")
        observed_fee_bps = features.number("observed_fee_bps", self.default_fee_bps)

        velocity_signal = _clamp(trade_rate / 30)
        participation_signal = _clamp(unique / 24)
        balance_signal = _clamp((buy_ratio - 0.42) / 0.35)
        progress_signal = _clamp(progress / 0.70)
        momentum_signal = _clamp(momentum / 0.35) * _clamp((1.5 - momentum) / 1.2)
        opportunity = _clamp(
            0.25 * velocity_signal
            + 0.25 * participation_signal
            + 0.18 * balance_signal
            + 0.20 * progress_signal
            + 0.12 * momentum_signal
        )

        concentration_risk = _clamp((hhi - 0.08) / 0.42)
        repetition_risk = _clamp((repeated - 0.15) / 0.60)
        coordination_risk = _clamp((same_slot - 0.20) / 0.65)
        creator_risk = 1.0 if creator_sells > 0 else 0.0
        parabolic_risk = _clamp((momentum - 0.70) / 1.30)
        danger = _clamp(
            0.28 * concentration_risk
            + 0.18 * repetition_risk
            + 0.14 * coordination_risk
            + 0.25 * creator_risk
            + 0.10 * drawdown
            + 0.05 * parabolic_risk
        )

        order_size = planned_order_size_sol or limits.order_size_sol
        impact = 1.0 if reserve_sol <= 0 else _clamp(order_size / max(reserve_sol, 0.000001))
        execution = _clamp(1 - impact * 6)
        round_trip_protocol_cost = 2 * _clamp(observed_fee_bps / 10_000, 0.0, 1.0)
        order_lamports = max(1, int(order_size * 1_000_000_000))
        round_trip_network_cost = 2 * self.one_way_network_fee_lamports / order_lamports
        # This is a dimensionless ranking heuristic, not a calibrated return forecast.
        net_edge = (
            opportunity * 0.22
            - danger * 0.32
            - impact * 1.8
            - round_trip_protocol_cost
            - round_trip_network_cost
        )
        confidence = features.data_confidence
        composite = round(
            100
            * _clamp(
                opportunity * 0.45 + (1 - danger) * 0.25 + execution * 0.15 + confidence * 0.15
            )
        )

        reasons = _reasons(
            velocity_signal=velocity_signal,
            participation_signal=participation_signal,
            balance_signal=balance_signal,
            progress_signal=progress_signal,
            momentum_signal=momentum_signal,
            impact=impact,
            danger=danger,
            confidence=confidence,
        )
        blockers = list(features.hard_flags)
        if age < 15:
            blockers.append("needs_at_least_15_seconds_of_history")
        if trades < 8:
            blockers.append("needs_at_least_8_observed_trades")
        if unique < 5:
            blockers.append("needs_at_least_5_unique_wallets")
        if confidence < limits.min_confidence:
            blockers.append("data_confidence_below_risk_mode_minimum")
        if danger > limits.max_danger:
            blockers.append("danger_above_risk_mode_limit")
        if impact > limits.max_price_impact:
            blockers.append("estimated_price_impact_above_limit")
        if net_edge < limits.min_net_edge_index:
            blockers.append("heuristic_net_edge_below_minimum")

        unreliable = any(
            item in blockers
            for item in (
                "missing_curve_reserves",
                "stale_market_data",
                "curve_complete_route_unconfirmed",
                "unsupported_quote_mint_v1",
                "unsupported_token_program",
                "mint_safety_unverified",
                "mint_account_failed_safety_checks",
            )
        )
        learning = age < 15 or trades < 8 or unique < 5
        if unreliable:
            action = DecisionAction.ABSTAIN
        elif learning:
            action = DecisionAction.WATCH
        elif blockers:
            action = DecisionAction.PASS
        else:
            action = DecisionAction.ENTER

        return Decision(
            decision_id=uuid.uuid4().hex,
            mint=features.mint,
            symbol=features.symbol,
            action=action,
            risk_mode=mode,
            score=DecisionScore(
                opportunity=opportunity,
                danger=danger,
                execution=execution,
                confidence=confidence,
                net_edge_index=net_edge,
                composite=composite,
            ),
            reasons=reasons,
            blockers=list(dict.fromkeys(blockers)),
            feature_snapshot=features,
            model_version=self.version,
            planned_order_size_sol=order_size,
        )


def _reasons(**signals: float) -> list[str]:
    labels = {
        "velocity_signal": "Trading velocity is building",
        "participation_signal": "Participation is spread across more wallets",
        "balance_signal": "Buy demand currently exceeds sell demand",
        "progress_signal": "The bonding curve has meaningful progress",
        "momentum_signal": "Short-term momentum is positive but not extreme",
    }
    ranked = sorted(
        ((key, value) for key, value in signals.items() if key in labels),
        key=lambda item: item[1],
        reverse=True,
    )
    reasons = [labels[key] for key, value in ranked[:3] if value >= 0.25]
    if signals["impact"] > 0.03:
        reasons.append("The selected paper size has noticeable price impact")
    if signals["danger"] > 0.35:
        reasons.append("Manipulation or concentration risk is elevated")
    if signals["confidence"] < 0.65:
        reasons.append("The evidence set is still incomplete")
    return reasons or ["Not enough reliable evidence has accumulated yet"]


def deterministic_explanation(decision: Decision) -> str:
    action = decision.action.value.upper()
    score = decision.score
    opening = (
        f"{action} because opportunity was {score.opportunity:.0%}, danger was "
        f"{score.danger:.0%}, data confidence was {score.confidence:.0%}, and the cost-aware "
        f"net-edge heuristic was {score.net_edge_index:+.1%}."
    )
    evidence = " Key evidence: " + "; ".join(decision.reasons[:2]) + "." if decision.reasons else ""
    blocked = (
        " The main blocker was " + decision.blockers[0].replace("_", " ") + "."
        if decision.blockers
        else " The configured risk gates passed."
    )
    return opening + evidence + blocked
