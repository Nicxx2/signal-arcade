from __future__ import annotations

import uuid

from ..models import (
    RISK_LIMITS,
    Decision,
    DecisionAction,
    DecisionScore,
    FeatureSnapshot,
    IntegrityAssessment,
    MarketIntegrityState,
    RiskLimits,
    RiskMode,
)
from ..strategy import (
    BASELINE_VERSION,
    INTEGRITY_POLICY_VERSION,
    LEGACY_BASELINE_VERSION,
    PREVIOUS_INTEGRITY_POLICY_VERSION,
    SUPPORTED_BASELINE_VERSIONS,
    UNCERTAIN_INTEGRITY_HOLD_SCORE,
    integrity_policy_for_baseline,
)

INTEGRITY_MIN_SAMPLE_COUNT = 24
INTEGRITY_MIN_AGE_SECONDS = 30.0
INTEGRITY_MIN_COVERAGE = 0.75


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class DecisionEngine:
    """Transparent V1 baseline. It abstains when evidence is unreliable."""

    version = BASELINE_VERSION

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
        baseline_version: str | None = None,
    ) -> Decision:
        active_version = baseline_version or self.version
        if active_version not in SUPPORTED_BASELINE_VERSIONS:
            raise ValueError(f"unsupported baseline version: {active_version}")
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
        integrity = (
            assess_market_integrity(
                features,
                policy_version=integrity_policy_for_baseline(active_version),
            )
            if active_version != LEGACY_BASELINE_VERSION
            else None
        )
        if integrity is not None and integrity.state in {
            MarketIntegrityState.SUSPICIOUS,
            MarketIntegrityState.SEVERE,
        }:
            danger = _clamp(danger + 0.22 * integrity.score)

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
        if integrity is not None and integrity.state == MarketIntegrityState.SEVERE:
            blockers.append("market_integrity_severe")
        if active_version == BASELINE_VERSION and integrity is not None:
            # New launches may satisfy the fast trader's basic 15-second gate before the
            # manipulation classifier has a complete sample.  v1.4 waits for that fuller
            # evidence instead of treating "not yet known" as safe.  Once mature, one extreme
            # isolated signal remains uncertain rather than being mislabeled as manipulation,
            # but the Baseline waits for it to clear or gain corroboration before entering.
            integrity_is_mature = (
                integrity.sample_count >= INTEGRITY_MIN_SAMPLE_COUNT
                and age >= INTEGRITY_MIN_AGE_SECONDS
                and integrity.coverage >= INTEGRITY_MIN_COVERAGE
            )
            if not integrity_is_mature:
                blockers.append("market_integrity_evidence_not_mature")
            elif (
                integrity.state == MarketIntegrityState.UNCERTAIN
                and integrity.category_count > 0
                and integrity.score >= UNCERTAIN_INTEGRITY_HOLD_SCORE
            ):
                blockers.append("market_integrity_uncertain_high_risk")
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
            model_version=active_version,
            planned_order_size_sol=order_size,
            integrity_assessment=integrity,
        )


def assess_market_integrity(
    features: FeatureSnapshot,
    *,
    policy_version: str = INTEGRITY_POLICY_VERSION,
) -> IntegrityAssessment:
    """Classify manipulation evidence without treating missing or tiny samples as safe.

    The conclusion requires corroboration across independent evidence categories. A single
    market-maker-like pattern, a short burst, or incomplete wallet metadata remains uncertain.
    """

    if policy_version not in {
        PREVIOUS_INTEGRITY_POLICY_VERSION,
        INTEGRITY_POLICY_VERSION,
    }:
        raise ValueError(f"unsupported integrity policy version: {policy_version}")

    sample_count = max(0, int(features.number("trade_count_5m")))
    age_seconds = max(0.0, features.number("age_seconds"))
    metric_names: tuple[str, ...] = (
        "round_trip_wallet_ratio",
        "round_trip_volume_ratio",
        "net_quote_flow_ratio",
        "side_alternation_ratio",
        "quantized_amount_repeat_ratio",
        "slot_concentration_hhi",
        "price_direction_consistency",
        "multi_trade_signature_ratio",
    )
    if policy_version == INTEGRITY_POLICY_VERSION:
        metric_names = (
            "wallet_volume_hhi",
            "single_trade_wallet_ratio",
            *metric_names,
        )
    available: dict[str, tuple[float, float]] = {}
    for name in metric_names:
        metric = _integrity_metric(features, name)
        if metric is not None:
            available[name] = metric

    category_scores: dict[str, float] = {}
    evidence: list[str] = []

    wallet_score = max(
        _risk_above(available.get("round_trip_wallet_ratio"), 0.30, 0.70),
        _risk_above(available.get("round_trip_volume_ratio"), 0.45, 0.85),
    )
    if wallet_score >= 0.55:
        category_scores["wallet_loops"] = wallet_score
        evidence.append("Repeated wallet round trips dominate participation or volume")

    if policy_version == INTEGRITY_POLICY_VERSION:
        # Neither concentration nor one-trade participation is suspicious by itself. Together,
        # at extreme levels, they describe a distinct dispersed-activity risk: most wallets appear
        # only once while very little of the traded value is economically independent. Keeping it
        # as one category prevents a lone whale or an organic launch burst from becoming a veto.
        dispersion_signals = sorted(
            (
                _risk_above(available.get("wallet_volume_hhi"), 0.35, 0.85),
                _risk_above(available.get("single_trade_wallet_ratio"), 0.80, 0.98),
            ),
            reverse=True,
        )
        dispersion_score = (
            (dispersion_signals[0] + dispersion_signals[1]) / 2
            if dispersion_signals[1] >= 0.35
            else dispersion_signals[0] * 0.50
        )
        if dispersion_score >= 0.55:
            category_scores["concentrated_dispersion"] = dispersion_score
            evidence.append(
                "One-trade participation accompanies extremely concentrated traded volume"
            )

    flow_score = _risk_below(available.get("net_quote_flow_ratio"), 0.28, 0.06)
    if flow_score >= 0.55:
        category_scores["low_net_flow"] = flow_score
        evidence.append("Gross trading volume produces unusually little net quote flow")

    structure_signals = sorted(
        (
            _risk_above(available.get("side_alternation_ratio"), 0.68, 0.92),
            _risk_above(available.get("quantized_amount_repeat_ratio"), 0.38, 0.78),
            _risk_above(available.get("slot_concentration_hhi"), 0.24, 0.62),
            _risk_above(available.get("multi_trade_signature_ratio"), 0.12, 0.50),
        ),
        reverse=True,
    )
    structure_score = (
        (structure_signals[0] + structure_signals[1]) / 2
        if structure_signals[1] >= 0.35
        else structure_signals[0] * 0.50
    )
    if structure_score >= 0.55:
        category_scores["trade_structure"] = structure_score
        evidence.append("Trade timing, ordering, or sizing repeats in a coordinated pattern")

    path_score = _risk_above(available.get("price_direction_consistency"), 0.84, 0.98)
    if path_score >= 0.55:
        category_scores["price_path"] = path_score
        evidence.append("The observed price path is unusually one-directional")

    # Missing metrics remain zero coverage instead of disappearing from the denominator. This
    # prevents a handful of pristine fields from making an incomplete sample look clean.
    coverage = sum(quality for _, quality in available.values()) / len(metric_names)
    category_count = len(category_scores)
    score = sum(category_scores.values()) / category_count if category_count else 0.0
    eligible = (
        sample_count >= INTEGRITY_MIN_SAMPLE_COUNT
        and age_seconds >= INTEGRITY_MIN_AGE_SECONDS
        and coverage >= INTEGRITY_MIN_COVERAGE
    )

    if not eligible:
        state = MarketIntegrityState.UNCERTAIN
        evidence.insert(0, "More time, trades, or complete stream fields are needed")
    elif category_count >= 3 and score >= 0.70:
        state = MarketIntegrityState.SEVERE
    elif category_count >= 2 and score >= 0.55:
        state = MarketIntegrityState.SUSPICIOUS
    elif category_count == 0:
        state = MarketIntegrityState.CLEAN
        evidence.append("No corroborated manipulation pattern is present in the usable sample")
    else:
        state = MarketIntegrityState.UNCERTAIN
        evidence.append("An isolated pattern is not enough to classify the market")

    return IntegrityAssessment(
        policy_version=policy_version,
        state=state,
        score=_clamp(score),
        coverage=_clamp(coverage),
        sample_count=sample_count,
        category_count=category_count,
        categories=list(category_scores),
        evidence=evidence,
    )


def _integrity_metric(features: FeatureSnapshot, name: str) -> tuple[float, float] | None:
    value = features.values.get(name)
    if (
        value is None
        or value.value is None
        or isinstance(value.value, bool)
        or value.missing_reason is not None
        or value.quality < 0.75
    ):
        return None
    try:
        numeric = float(value.value)
    except (TypeError, ValueError):
        return None
    return _clamp(numeric), value.quality


def _risk_above(metric: tuple[float, float] | None, start: float, full: float) -> float:
    if metric is None:
        return 0.0
    value, quality = metric
    return _clamp((value - start) / max(full - start, 0.000001)) * quality


def _risk_below(metric: tuple[float, float] | None, start: float, full: float) -> float:
    if metric is None:
        return 0.0
    value, quality = metric
    return _clamp((start - value) / max(start - full, 0.000001)) * quality


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
