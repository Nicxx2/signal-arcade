from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from statistics import fmean
from typing import Any

from ..config import Settings
from ..database import Database
from ..models import (
    RISK_LIMITS,
    Decision,
    DecisionAction,
    LearningAssessment,
    LearningCheckpoint,
    LearningMode,
    LearningModel,
    LearningObservation,
    LearningObservationStatus,
    RiskMode,
)
from ..paper.curve_math import quote_buy, quote_sell
from .features import TokenState

PRIMARY_HORIZON_SECONDS = 300
LEARNING_HORIZONS_SECONDS = (60, PRIMARY_HORIZON_SECONDS, 600, 900, 1_200)
CHECKPOINT_GRACE_SECONDS = 90
MINIMUM_TRAINING_SAMPLES = 80
MINIMUM_FIT_SAMPLES = 40
MINIMUM_VALIDATION_SAMPLES = 20
MODEL_WINDOW_OBSERVATIONS = 1_000
ENTRY_MINIMUM_OUTCOME_AVAILABILITY = 0.70
ENTRY_MINIMUM_RMSE_RELATIVE_IMPROVEMENT = 0.02
ENTRY_MINIMUM_TOP_RETURN = 0.01
ENTRY_MINIMUM_TOP_UPLIFT = 0.01
ENTRY_MINIMUM_POLICY_SAMPLES = 20
ENTRY_MINIMUM_POLICY_VETOES = 5
ENTRY_MINIMUM_POLICY_UPLIFT = 0.0
ENTRY_POLICY_Z_SCORE = 1.96
ENTRY_MINIMUM_IN_DISTRIBUTION_FRACTION = 0.95
MODEL_SUPPORT_Z_SCORE = 6.0
MINIMUM_FEATURE_SCALE = 0.01
HOLD_TIMING_MINIMUM_SAMPLES = 60
HOLD_TIMING_MINIMUM_AVAILABILITY = 0.70
HOLD_TIMING_MINIMUM_UPLIFT = 0.01
HOLD_TIMING_Z_SCORE = 1.96
HOLD_TIMING_WINDOW_OBSERVATIONS = 1_000
RETRAIN_SAMPLE_INTERVAL = 10
MAX_COMPLETED_OBSERVATIONS = 5_000
MAX_MODEL_VERSIONS = 1_000
LEARNER_VERSION_PREFIX = "learner-v4-"
ACTIVE_HEALTH_MINIMUM_SAMPLES = 30
ACTIVE_HEALTH_WINDOW = 60
ACTIVE_HEALTH_MINIMUM_AVAILABILITY = 0.70
ACTIVE_HEALTH_HARM_MARGIN = 0.01
ACTIVE_HEALTH_Z_SCORE = 1.96
INTEGRITY_FEATURE_NAMES = (
    "single_trade_wallet_ratio",
    "round_trip_wallet_ratio",
    "round_trip_volume_ratio",
    "net_quote_flow_ratio",
    "side_alternation_ratio",
    "quantized_amount_repeat_ratio",
    "slot_concentration_hhi",
    "price_direction_consistency",
)
FEATURE_NAMES = (
    "opportunity",
    "danger",
    "execution",
    "confidence",
    "buy_ratio",
    "wallet_breadth",
    "concentration",
    "repetition",
    "coordination",
    "curve_progress",
    "momentum",
    "drawdown",
    "reserve_depth",
    *INTEGRITY_FEATURE_NAMES,
)
FEATURE_LABELS = {
    "opportunity": "baseline opportunity",
    "danger": "measured danger",
    "execution": "execution quality",
    "confidence": "evidence confidence",
    "buy_ratio": "buy/sell balance",
    "wallet_breadth": "wallet participation",
    "concentration": "wallet concentration",
    "repetition": "repeated trade sizing",
    "coordination": "same-slot coordination",
    "curve_progress": "bonding-curve progress",
    "momentum": "short-term momentum",
    "drawdown": "recent token drawdown",
    "reserve_depth": "on-chain reserve depth",
    "single_trade_wallet_ratio": "one-trade wallet share",
    "round_trip_wallet_ratio": "wallet round trips",
    "round_trip_volume_ratio": "round-trip wallet volume",
    "net_quote_flow_ratio": "net flow versus gross volume",
    "side_alternation_ratio": "buy/sell alternation",
    "quantized_amount_repeat_ratio": "clustered trade sizing",
    "slot_concentration_hhi": "slot concentration",
    "price_direction_consistency": "one-way price path",
}
STRUCTURAL_FLAGS = {
    "missing_curve_reserves",
    "stale_market_data",
    "curve_complete_route_unconfirmed",
    "unsupported_quote_mint_v1",
    "unsupported_token_program",
    "mint_safety_unverified",
    "mint_account_failed_safety_checks",
}


class LearningEngine:
    """Local, versioned challenger trained only on forward live-paper outcomes."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        configuration_fingerprint: Callable[[], str | None] | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.configuration_fingerprint = configuration_fingerprint or (lambda: None)
        try:
            self.current_risk_mode = RiskMode(
                database.get_setting("risk_mode", RiskMode.BALANCED.value)
            )
        except ValueError:
            self.current_risk_mode = RiskMode.BALANCED
        self.observations = {item.mint: item for item in database.list_learning_observations()}
        self.models = database.list_learning_models()
        # Timing validation is read on every active market event. Recompute it only when
        # a checkpoint/prune changes the chronological evidence, keeping long runs cheap.
        self._timing_revision = 0
        self._timing_cache: dict[RiskMode, tuple[int, dict[str, Any]]] = {}
        self.disabled_model_versions = set(database.get_setting("disabled_learning_models", []))
        self.reactivation_after_outcomes = int(
            database.get_setting("learning_reactivation_after_outcomes", 0)
        )
        saved_suspension = database.get_setting("learning_last_suspension", None)
        self.last_suspension = saved_suspension if isinstance(saved_suspension, dict) else None
        current_usable = len(self._training_rows())
        self.outcomes_seen = max(
            current_usable,
            int(database.get_setting("learning_outcomes_seen", current_usable)),
        )
        database.set_setting("learning_outcomes_seen", self.outcomes_seen)
        try:
            self.mode = LearningMode(
                database.get_setting("learning_mode", LearningMode.SHADOW.value)
            )
        except ValueError:
            self.mode = LearningMode.SHADOW
            database.set_setting("learning_mode", self.mode.value)
        active_version = str(database.get_setting("active_learning_model", ""))
        self.active_model = next(
            (
                model
                for model in self.models
                if model.version == active_version
                and self._model_is_eligible(model, require_newer_than_suspension=False)
            ),
            None,
        )
        if self.mode != LearningMode.ACTIVE:
            self.active_model = None
        elif self.active_model is None:
            self.mode = LearningMode.SHADOW
            database.set_setting("learning_mode", self.mode.value)
            database.set_setting("active_learning_model", "")

    @property
    def pending_mints(self) -> set[str]:
        return {
            mint
            for mint, observation in self.observations.items()
            if observation.status == LearningObservationStatus.PENDING
        }

    def has_pending_mint(self, mint: str) -> bool:
        """Check one live outcome without rebuilding the complete pending-mint set."""

        observation = self.observations.get(mint)
        return bool(
            observation is not None and observation.status == LearningObservationStatus.PENDING
        )

    @property
    def latest_model(self) -> LearningModel | None:
        return self._latest_model_for_context(
            self.current_risk_mode,
            self.configuration_fingerprint(),
        )

    def set_risk_mode(self, mode: RiskMode) -> None:
        """Keep influence inside the exact risk cohort that earned validation."""

        self.current_risk_mode = mode
        if (
            self.mode == LearningMode.ACTIVE
            and self.active_model is not None
            and self.active_model.risk_mode != mode
        ):
            self.set_mode(LearningMode.SHADOW)

    def configuration_changed(self) -> None:
        """A new fee/provider/latency policy invalidates an active artifact's provenance."""

        self._invalidate_timing_validation()
        if (
            self.mode == LearningMode.ACTIVE
            and self.active_model is not None
            and self.active_model.configuration_fingerprint != self.configuration_fingerprint()
        ):
            self.set_mode(LearningMode.SHADOW)

    def set_mode(self, mode: LearningMode) -> None:
        if mode == LearningMode.ACTIVE:
            candidate = self._activation_candidate()
            if candidate is None:
                raise ValueError(
                    "the newest challenger must pass the current forward and suspension gates "
                    "before activation"
                )
            self._activate_model(candidate)
        elif self.mode == LearningMode.ACTIVE:
            self.active_model = None
            self.database.set_setting("active_learning_model", "")
        self.mode = mode
        self.database.set_setting("learning_mode", mode.value)

    def register(
        self,
        decision: Decision,
        state: TokenState,
        *,
        live: bool,
        evaluation_actionable: bool = False,
    ) -> bool:
        """Create one independent, executable counterfactual per eligible live token."""
        if not live or self.mode == LearningMode.OFF or state.mint in self.observations:
            return False
        if decision.action not in {DecisionAction.ENTER, DecisionAction.PASS}:
            return False
        if STRUCTURAL_FLAGS.intersection(decision.feature_snapshot.hard_flags):
            return False
        features = decision.feature_snapshot
        if (
            features.number("age_seconds") < 15
            or features.number("trade_count_5m") < 8
            or features.number("unique_wallets_5m") < 5
        ):
            return False
        size_sol = decision.planned_order_size_sol or RISK_LIMITS[decision.risk_mode].order_size_sol
        fee_bps = state.fee_bps or self.settings.pump_fee_bps
        try:
            entry = quote_buy(
                virtual_token_reserves=state.virtual_token_reserves,
                virtual_sol_reserves=state.virtual_quote_reserves,
                real_token_reserves=state.real_token_reserves,
                wallet_trade_budget_lamports=max(1, int(size_sol * 1_000_000_000)),
                fee_bps=fee_bps,
                network_fee_lamports=(
                    self.settings.network_fee_lamports + self.settings.priority_fee_lamports
                ),
            )
        except ValueError:
            return False
        feature_vector = _feature_vector(decision)
        if feature_vector is None:
            # The baseline can still act, but incomplete stream evidence must not become a
            # fabricated all-zero learner row.
            return False
        evaluation_model = (
            self.active_model
            if self.mode == LearningMode.ACTIVE
            and self.active_model is not None
            and self.active_model.risk_mode == decision.risk_mode
            and self.active_model.configuration_fingerprint == decision.configuration_fingerprint
            else None
        )
        evaluation_in_distribution = bool(
            evaluation_model is not None and _within_model_support(evaluation_model, feature_vector)
        )
        observation = LearningObservation(
            observation_id="learning-" + decision.decision_id,
            decision_id=decision.decision_id,
            mint=decision.mint,
            symbol=decision.symbol,
            created_at=decision.created_at,
            baseline_action=decision.action,
            risk_mode=decision.risk_mode,
            baseline_edge_index=decision.score.net_edge_index,
            baseline_composite=decision.score.composite,
            features=feature_vector,
            token_units=entry.token_units,
            entry_cost_lamports=entry.wallet_sol_lamports,
            entry_price_impact_fraction=entry.price_impact_fraction,
            fee_bps=fee_bps,
            evaluation_model_version=(
                evaluation_model.version if evaluation_model is not None else None
            ),
            evaluation_prediction=(
                _predict(evaluation_model, feature_vector) if evaluation_model is not None else None
            ),
            evaluation_validation_rmse=(
                evaluation_model.validation_rmse if evaluation_model is not None else None
            ),
            baseline_actionable=bool(evaluation_actionable),
            evaluation_actionable=bool(
                evaluation_model is not None
                and evaluation_actionable
                and evaluation_in_distribution
            ),
            baseline_reasons=list(decision.reasons),
            baseline_blockers=list(decision.blockers),
            opportunity_score=decision.score.opportunity,
            danger_score=decision.score.danger,
            execution_score=decision.score.execution,
            confidence_score=decision.score.confidence,
            season_id=decision.season_id,
            season_profile_fingerprint=decision.season_profile_fingerprint,
            configuration_fingerprint=decision.configuration_fingerprint,
        )
        self.observations[state.mint] = observation
        self.database.save_learning_observation(observation)
        return True

    def observe_market(self, state: TokenState, now: datetime, *, live: bool) -> int:
        if not live:
            return 0
        observation = self.observations.get(state.mint)
        if observation is None or observation.status != LearningObservationStatus.PENDING:
            return 0
        age = max(0.0, (now - observation.created_at).total_seconds())
        changed = 0
        primary_became_available = False
        for horizon in LEARNING_HORIZONS_SECONDS:
            key = str(horizon)
            if key in observation.checkpoints or age < horizon:
                continue
            if age > horizon + CHECKPOINT_GRACE_SECONDS:
                observation.checkpoints[key] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=now,
                    missing_reason="no_fresh_trade_near_horizon",
                )
            else:
                try:
                    exit_quote = quote_sell(
                        virtual_token_reserves=state.virtual_token_reserves,
                        virtual_sol_reserves=state.virtual_quote_reserves,
                        token_units=observation.token_units,
                        fee_bps=state.fee_bps or observation.fee_bps,
                        network_fee_lamports=(
                            self.settings.network_fee_lamports + self.settings.priority_fee_lamports
                        ),
                    )
                    net_return = (
                        exit_quote.wallet_sol_lamports - observation.entry_cost_lamports
                    ) / observation.entry_cost_lamports
                    observation.checkpoints[key] = LearningCheckpoint(
                        horizon_seconds=horizon,
                        observed_at=now,
                        net_return=max(-1.0, min(10.0, net_return)),
                        exit_value_lamports=exit_quote.wallet_sol_lamports,
                    )
                    primary_became_available = horizon == PRIMARY_HORIZON_SECONDS
                except ValueError:
                    observation.checkpoints[key] = LearningCheckpoint(
                        horizon_seconds=horizon,
                        observed_at=now,
                        missing_reason="executable_exit_quote_unavailable",
                    )
            changed += 1
        if len(observation.checkpoints) == len(LEARNING_HORIZONS_SECONDS):
            observation.status = LearningObservationStatus.COMPLETE
        if changed:
            self.database.save_learning_observation(observation)
            self._invalidate_timing_validation()
        if primary_became_available:
            self._record_usable_outcome()
            self._retrain_if_ready()
        if observation.status == LearningObservationStatus.COMPLETE:
            self._prune_complete_history()
        return changed

    def expire_checkpoints(self, now: datetime) -> int:
        changed = 0
        primary_changed = False
        for observation in self.observations.values():
            if observation.status != LearningObservationStatus.PENDING:
                continue
            age = max(0.0, (now - observation.created_at).total_seconds())
            item_changed = False
            for horizon in LEARNING_HORIZONS_SECONDS:
                key = str(horizon)
                if key in observation.checkpoints or age <= horizon + CHECKPOINT_GRACE_SECONDS:
                    continue
                observation.checkpoints[key] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=now,
                    missing_reason="no_fresh_trade_near_horizon",
                )
                item_changed = True
                changed += 1
                primary_changed = primary_changed or horizon == PRIMARY_HORIZON_SECONDS
            if len(observation.checkpoints) == len(LEARNING_HORIZONS_SECONDS):
                observation.status = LearningObservationStatus.COMPLETE
            if item_changed:
                self.database.save_learning_observation(observation)
        if primary_changed:
            self._retrain_if_ready()
        if changed:
            self._prune_complete_history()
            self._invalidate_timing_validation()
        return changed

    def assess(
        self,
        decision: Decision,
        *,
        live: bool,
        baseline_actionable: bool = True,
    ) -> Decision:
        model = (
            self.active_model
            if self.mode == LearningMode.ACTIVE
            else self._latest_model_for_context(
                decision.risk_mode,
                decision.configuration_fingerprint,
            )
        )
        if not live or model is None or not _model_shape_valid(model):
            return decision
        features = _feature_vector(decision)
        if features is None:
            return decision
        prediction = _predict(model, features)
        conservative = max(-1.0, min(10.0, prediction - model.validation_rmse))
        in_distribution = _within_model_support(model, features)
        applied = bool(
            self.mode == LearningMode.ACTIVE
            and self.active_model is not None
            and self.active_model.qualified
            and model.risk_mode == decision.risk_mode
            and model.configuration_fingerprint == decision.configuration_fingerprint
            and in_distribution
            and decision.action == DecisionAction.ENTER
            and baseline_actionable
        )
        verdict = (
            "out_of_distribution"
            if not in_distribution
            else "supports_entry"
            if conservative > 0
            else "caution"
        )
        assessment = LearningAssessment(
            model_version=model.version,
            predicted_net_return=prediction,
            conservative_net_return=conservative,
            validation_rmse=model.validation_rmse,
            applied=applied,
            verdict=verdict,
        )
        updates: dict[str, Any] = {"learning_assessment": assessment}
        if applied:
            updates["model_version"] = f"{decision.model_version}+{model.version}"
            if conservative <= 0:
                updates["action"] = DecisionAction.PASS
                updates["blockers"] = [
                    *decision.blockers,
                    "learner_conservative_return_not_positive",
                ]
                updates["reasons"] = [
                    *decision.reasons,
                    "The proven learner preserved cash because its conservative outcome "
                    "was not positive",
                ]
            else:
                updates["reasons"] = [
                    *decision.reasons,
                    "The proven learner also supports this baseline entry",
                ]
        return decision.model_copy(update=updates)

    def status(self, *, demo_mode: bool) -> dict[str, Any]:
        samples = self._training_rows(
            mode=self.current_risk_mode,
            configuration_fingerprint=self.configuration_fingerprint(),
            match_configuration=True,
        )
        timing_validation = {mode.value: self.hold_timing_validation(mode) for mode in RISK_LIMITS}
        activation_candidate = self._activation_candidate()
        active_health = self.active_model_health()
        entry_availability = self.entry_outcome_availability()
        pending = sum(
            item.status == LearningObservationStatus.PENDING for item in self.observations.values()
        )
        missing = sum(
            (checkpoint := item.checkpoints.get(str(PRIMARY_HORIZON_SECONDS))) is not None
            and checkpoint.net_return is None
            for item in self.observations.values()
        )
        latest = self.latest_model
        if self.mode == LearningMode.OFF:
            state = "paused"
        elif self.mode == LearningMode.ACTIVE:
            state = "active"
        elif latest is None:
            state = "collecting"
        elif activation_candidate is not None:
            state = "ready"
        else:
            state = "challenger_testing"
        next_training = (
            max(0, MINIMUM_TRAINING_SAMPLES - len(samples))
            if latest is None
            else max(0, RETRAIN_SAMPLE_INTERVAL - (self.outcomes_seen - latest.outcomes_seen))
        )
        qualification_gates = _entry_qualification_gates(
            latest,
            usable_outcomes=len(samples),
            current_availability=entry_availability,
            activation_available=activation_candidate is not None,
        )
        return {
            "mode": self.mode.value,
            "state": state,
            "demo_excluded": True,
            "collecting_from_current_source": not demo_mode,
            "live_only": True,
            "observation_count": len(self.observations),
            "usable_outcome_count": len(samples),
            "pending_count": pending,
            "unavailable_outcome_count": missing,
            "minimum_training_samples": MINIMUM_TRAINING_SAMPLES,
            "retained_observation_limit": MAX_COMPLETED_OBSERVATIONS,
            "retained_model_limit": MAX_MODEL_VERSIONS,
            "model_window_observations": MODEL_WINDOW_OBSERVATIONS,
            "entry_outcome_availability": entry_availability,
            "outcomes_until_next_training": next_training,
            "challenger_interval_outcomes": RETRAIN_SAMPLE_INTERVAL,
            "horizons_seconds": list(LEARNING_HORIZONS_SECONDS),
            "horizon_performance": self.horizon_performance(),
            "recommended_hold_seconds": {
                mode.value: self.recommended_hold_seconds(mode) for mode in RISK_LIMITS
            },
            "hold_timing_validation": timing_validation,
            "adaptive_hold_applied": any(
                self.mode == LearningMode.ACTIVE and timing_validation[mode.value]["qualified"]
                for mode in RISK_LIMITS
            ),
            "latest_model": _model_summary(latest),
            "active_model": _model_summary(self.active_model),
            "active_model_health": active_health,
            "activation_available": activation_candidate is not None,
            "qualification_gates": qualification_gates,
            "qualification_passed": sum(gate["state"] == "passed" for gate in qualification_gates),
            "qualification_total": len(qualification_gates),
            "lessons": _lessons(latest),
            "guardrails": [
                "Never trains on synthetic Demo Market data",
                "Never overrides structural safety, confidence, danger, impact, or drawdown gates",
                "Can veto a baseline entry but cannot invent a new entry",
                "Uses forward outcomes after modeled entry, exit, protocol, and network costs",
                "Missing exit liquidity lowers a horizon's utility without inventing a sale price",
                "Entry activation requires at least 70% recent executable outcome availability",
                "Hold timing needs its own chronological validation before it can shorten a review",
                "Learned timing cannot postpone a review or bypass the absolute exit ceiling",
                "Outcome overlap is embargoed before every chronological validation section",
                "An active model returns to shadow if later unseen outcomes show confident harm",
                "Risk/configuration changes and unfamiliar features restore the baseline",
            ],
        }

    def horizon_performance(self) -> list[dict[str, Any]]:
        """Compare executable horizons while conservatively penalizing unavailable exits."""

        rows: list[dict[str, Any]] = []
        for horizon in LEARNING_HORIZONS_SECONDS:
            key = str(horizon)
            checkpoints = [
                checkpoint
                for observation in self.observations.values()
                if (checkpoint := observation.checkpoints.get(key)) is not None
            ]
            returns = [
                checkpoint.net_return
                for checkpoint in checkpoints
                if checkpoint.net_return is not None
            ]
            available_count = len(returns)
            observed_count = len(checkpoints)
            availability = available_count / observed_count if observed_count else 0.0
            mean_return = fmean(returns) if returns else None
            standard_error: float | None
            if len(returns) >= 2 and mean_return is not None:
                variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
                standard_error = math.sqrt(variance / len(returns))
            else:
                standard_error = 1.0 if returns else None
            conservative_return = (
                max(-1.0, mean_return - standard_error)
                if mean_return is not None and standard_error is not None
                else None
            )
            # No price is fabricated for missing checkpoints. For horizon selection only,
            # inability to obtain an executable quote carries worst-case utility.
            utility = (
                availability * conservative_return - (1 - availability)
                if conservative_return is not None
                else None
            )
            rows.append(
                {
                    "horizon_seconds": horizon,
                    "observed_count": observed_count,
                    "available_count": available_count,
                    "availability_fraction": availability,
                    "mean_net_return": mean_return,
                    "conservative_utility": utility,
                }
            )
        return rows

    def recommended_hold_seconds(self, mode: RiskMode) -> int:
        """Apply timing only after its own chronological validation and active opt-in."""

        limits = RISK_LIMITS[mode]
        if (
            self.mode != LearningMode.ACTIVE
            or self.active_model is None
            or not self._model_is_eligible(
                self.active_model,
                require_newer_than_suspension=False,
            )
            or self.active_model.risk_mode != mode
        ):
            return limits.max_hold_seconds
        assessment = self.hold_timing_validation(mode)
        return (
            int(assessment["selected_horizon_seconds"])
            if assessment["qualified"]
            else limits.max_hold_seconds
        )

    def hold_timing_validation(self, mode: RiskMode) -> dict[str, Any]:
        """Choose on older outcomes, then qualify only on a newer untouched section."""

        cached = self._timing_cache.get(mode)
        if cached is not None and cached[0] == self._timing_revision:
            return cached[1]

        baseline = RISK_LIMITS[mode].max_hold_seconds
        candidates = [horizon for horizon in LEARNING_HORIZONS_SECONDS if horizon <= baseline]
        rows = [
            observation
            for observation in sorted(self.observations.values(), key=lambda item: item.created_at)
            if observation.risk_mode == mode
            and observation.configuration_fingerprint == self.configuration_fingerprint()
            and str(baseline) in observation.checkpoints
            and all(str(horizon) in observation.checkpoints for horizon in candidates)
        ][-HOLD_TIMING_WINDOW_OBSERVATIONS:]
        sample_count = len(rows)
        validation_count = max(MINIMUM_VALIDATION_SAMPLES, sample_count // 3)
        raw_training = rows[: max(0, sample_count - validation_count)]
        validation = rows[len(raw_training) :]
        validation_start = validation[0].created_at if validation else None
        training = [
            observation
            for observation in raw_training
            if validation_start is not None
            and all(
                observation.checkpoints[str(horizon)].observed_at <= validation_start
                for horizon in candidates
            )
        ]
        training_count = len(training)
        embargoed_count = len(raw_training) - training_count
        empty = {
            "qualified": False,
            "selected_horizon_seconds": baseline,
            "baseline_horizon_seconds": baseline,
            "sample_count": sample_count,
            "training_count": training_count,
            "validation_count": min(validation_count, sample_count),
            "embargoed_count": embargoed_count,
            "selected_training_utility": None,
            "baseline_training_utility": None,
            "selected_validation_utility": None,
            "baseline_validation_utility": None,
            "validation_uplift_lower_bound": None,
            "validation_availability_fraction": 0.0,
        }
        if (
            sample_count < HOLD_TIMING_MINIMUM_SAMPLES
            or training_count < MINIMUM_VALIDATION_SAMPLES
        ):
            self._timing_cache[mode] = (self._timing_revision, empty)
            return empty

        training_utilities = {
            horizon: _mean_horizon_utility(training, horizon) for horizon in candidates
        }
        selected = max(
            candidates,
            key=lambda horizon: (training_utilities[horizon], horizon == baseline),
        )
        selected_training = training_utilities[selected]
        baseline_training = training_utilities[baseline]
        selected_validation = _mean_horizon_utility(validation, selected)
        baseline_validation = _mean_horizon_utility(validation, baseline)
        validation_deltas = [
            _checkpoint_utility(observation, selected) - _checkpoint_utility(observation, baseline)
            for observation in validation
        ]
        validation_uplift = fmean(validation_deltas)
        if len(validation_deltas) >= 2:
            variance = sum((value - validation_uplift) ** 2 for value in validation_deltas) / (
                len(validation_deltas) - 1
            )
            validation_uplift_lower = validation_uplift - HOLD_TIMING_Z_SCORE * math.sqrt(
                variance / len(validation_deltas)
            )
        else:
            validation_uplift_lower = validation_uplift
        validation_available = sum(
            observation.checkpoints[str(selected)].net_return is not None
            for observation in validation
        ) / len(validation)
        qualified = bool(
            selected != baseline
            and selected_training >= baseline_training + HOLD_TIMING_MINIMUM_UPLIFT
            and validation_uplift_lower >= HOLD_TIMING_MINIMUM_UPLIFT
            and validation_available >= HOLD_TIMING_MINIMUM_AVAILABILITY
        )
        result = {
            **empty,
            "qualified": qualified,
            "selected_horizon_seconds": selected,
            "selected_training_utility": selected_training,
            "baseline_training_utility": baseline_training,
            "selected_validation_utility": selected_validation,
            "baseline_validation_utility": baseline_validation,
            "validation_uplift_lower_bound": validation_uplift_lower,
            "validation_availability_fraction": validation_available,
        }
        self._timing_cache[mode] = (self._timing_revision, result)
        return result

    def active_model_health(self) -> dict[str, Any]:
        """Evaluate only predictions frozen before their later five-minute outcomes existed."""

        model = self.active_model if self.mode == LearningMode.ACTIVE else None
        if model is None:
            if self.last_suspension is not None:
                return dict(self.last_suspension)
            return {
                "state": "inactive",
                "model_version": None,
                "observed_count": 0,
                "usable_count": 0,
                "minimum_samples": ACTIVE_HEALTH_MINIMUM_SAMPLES,
                "availability_fraction": 0.0,
                "baseline_mean_return": None,
                "learner_mean_return": None,
                "estimated_uplift": None,
                "uplift_upper_bound": None,
                "supported_count": 0,
                "vetoed_count": 0,
                "winner_vetoed_count": 0,
            }

        resolved = [
            observation
            for observation in sorted(self.observations.values(), key=lambda item: item.created_at)
            if observation.evaluation_model_version == model.version
            and observation.baseline_action == DecisionAction.ENTER
            and observation.evaluation_actionable
            and str(PRIMARY_HORIZON_SECONDS) in observation.checkpoints
            and observation.evaluation_prediction is not None
            and observation.evaluation_validation_rmse is not None
        ][-ACTIVE_HEALTH_WINDOW:]
        usable = [
            observation
            for observation in resolved
            if observation.checkpoints[str(PRIMARY_HORIZON_SECONDS)].net_return is not None
        ]
        observed_count = len(resolved)
        usable_count = len(usable)
        availability = usable_count / observed_count if observed_count else 0.0
        baseline_returns = [
            observation.checkpoints[str(PRIMARY_HORIZON_SECONDS)].net_return
            for observation in usable
        ]
        supported = [
            bool(
                observation.evaluation_prediction is not None
                and observation.evaluation_validation_rmse is not None
                and observation.evaluation_prediction - observation.evaluation_validation_rmse > 0
            )
            for observation in usable
        ]
        learned_returns = [
            outcome if support else 0.0
            for outcome, support in zip(baseline_returns, supported, strict=True)
            if outcome is not None
        ]
        numeric_baseline = [outcome for outcome in baseline_returns if outcome is not None]
        deltas = [
            learned - baseline
            for learned, baseline in zip(learned_returns, numeric_baseline, strict=True)
        ]
        baseline_mean = fmean(numeric_baseline) if numeric_baseline else None
        learner_mean = fmean(learned_returns) if learned_returns else None
        uplift = fmean(deltas) if deltas else None
        uplift_upper: float | None
        if len(deltas) >= 2 and uplift is not None:
            variance = sum((value - uplift) ** 2 for value in deltas) / (len(deltas) - 1)
            uplift_upper = uplift + ACTIVE_HEALTH_Z_SCORE * math.sqrt(variance / len(deltas))
        else:
            uplift_upper = uplift
        enough_evidence = bool(
            usable_count >= ACTIVE_HEALTH_MINIMUM_SAMPLES
            and availability >= ACTIVE_HEALTH_MINIMUM_AVAILABILITY
        )
        unverifiable = bool(
            observed_count >= ACTIVE_HEALTH_MINIMUM_SAMPLES
            and availability < ACTIVE_HEALTH_MINIMUM_AVAILABILITY
        )
        degraded = bool(
            enough_evidence
            and uplift_upper is not None
            and uplift_upper < -ACTIVE_HEALTH_HARM_MARGIN
        )
        state = (
            "unverifiable"
            if unverifiable
            else "degraded"
            if degraded
            else "healthy"
            if enough_evidence
            else "collecting"
        )
        return {
            "state": state,
            "model_version": model.version,
            "observed_count": observed_count,
            "usable_count": usable_count,
            "minimum_samples": ACTIVE_HEALTH_MINIMUM_SAMPLES,
            "availability_fraction": availability,
            "baseline_mean_return": baseline_mean,
            "learner_mean_return": learner_mean,
            "estimated_uplift": uplift,
            "uplift_upper_bound": uplift_upper,
            "supported_count": sum(supported),
            "vetoed_count": len(supported) - sum(supported),
            "winner_vetoed_count": sum(
                not support and outcome is not None and outcome > 0
                for support, outcome in zip(supported, baseline_returns, strict=True)
            ),
        }

    def entry_outcome_availability(
        self,
        mode: RiskMode | None = None,
        configuration_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        """Measure recent primary-label observability without inventing missing returns."""

        selected_mode = mode or self.current_risk_mode
        selected_configuration = (
            self.configuration_fingerprint()
            if configuration_fingerprint is None
            else configuration_fingerprint
        )
        key = str(PRIMARY_HORIZON_SECONDS)
        resolved = [
            observation
            for observation in sorted(self.observations.values(), key=lambda item: item.created_at)
            if observation.risk_mode == selected_mode
            and observation.configuration_fingerprint == selected_configuration
            and _observation_features_complete(observation)
            and key in observation.checkpoints
        ][-MODEL_WINDOW_OBSERVATIONS:]
        available_count = sum(
            observation.checkpoints[key].net_return is not None for observation in resolved
        )
        observed_count = len(resolved)
        fraction = available_count / observed_count if observed_count else 0.0
        return {
            "observed_count": observed_count,
            "available_count": available_count,
            "availability_fraction": fraction,
            "minimum_fraction": ENTRY_MINIMUM_OUTCOME_AVAILABILITY,
            "qualified": bool(
                observed_count >= MINIMUM_TRAINING_SAMPLES
                and fraction >= ENTRY_MINIMUM_OUTCOME_AVAILABILITY
            ),
        }

    def _model_is_eligible(
        self,
        model: LearningModel,
        *,
        require_newer_than_suspension: bool = True,
    ) -> bool:
        return bool(
            model.qualified
            and model.version.startswith(LEARNER_VERSION_PREFIX)
            and _model_shape_valid(model)
            and model.risk_mode == self.current_risk_mode
            and model.configuration_fingerprint == self.configuration_fingerprint()
            and model.validation_in_distribution_fraction >= ENTRY_MINIMUM_IN_DISTRIBUTION_FRACTION
            and model.policy_validation_count >= ENTRY_MINIMUM_POLICY_SAMPLES
            and model.policy_veto_count >= ENTRY_MINIMUM_POLICY_VETOES
            and model.policy_uplift_lower_bound is not None
            and model.policy_uplift_lower_bound > ENTRY_MINIMUM_POLICY_UPLIFT
            and model.version not in self.disabled_model_versions
            and (
                not require_newer_than_suspension
                or model.outcomes_seen > self.reactivation_after_outcomes
            )
        )

    def _activation_candidate(self) -> LearningModel | None:
        latest = self.latest_model
        return (
            latest
            if latest is not None
            and self._model_is_eligible(latest)
            and self.entry_outcome_availability()["qualified"]
            else None
        )

    def _latest_model_for_context(
        self,
        mode: RiskMode,
        configuration_fingerprint: str | None,
    ) -> LearningModel | None:
        return next(
            (
                model
                for model in reversed(self.models)
                if model.version.startswith(LEARNER_VERSION_PREFIX)
                and model.risk_mode == mode
                and model.configuration_fingerprint == configuration_fingerprint
            ),
            None,
        )

    def _activate_model(self, model: LearningModel) -> None:
        self.active_model = model
        self.reactivation_after_outcomes = 0
        self.last_suspension = None
        self.database.set_setting("active_learning_model", model.version)
        self.database.set_setting("learning_reactivation_after_outcomes", 0)
        self.database.set_setting("learning_last_suspension", None)

    def _govern_active_model(self) -> None:
        if self.mode != LearningMode.ACTIVE or self.active_model is None:
            return
        health = self.active_model_health()
        if health["state"] in {"degraded", "unverifiable"}:
            version = self.active_model.version
            self.disabled_model_versions.add(version)
            self.reactivation_after_outcomes = self.outcomes_seen
            self.last_suspension = {
                **health,
                "state": "suspended",
                "suspension_reason": health["state"],
                "suspended_at": datetime.now(UTC).isoformat(),
            }
            self.active_model = None
            self.mode = LearningMode.SHADOW
            self.database.set_setting(
                "disabled_learning_models", sorted(self.disabled_model_versions)
            )
            self.database.set_setting(
                "learning_reactivation_after_outcomes", self.reactivation_after_outcomes
            )
            self.database.set_setting("learning_last_suspension", self.last_suspension)
            self.database.set_setting("active_learning_model", "")
            self.database.set_setting("learning_mode", self.mode.value)
            return
        candidate = self._activation_candidate()
        if (
            health["usable_count"] >= ACTIVE_HEALTH_MINIMUM_SAMPLES
            and candidate is not None
            and candidate.outcomes_seen > self.active_model.outcomes_seen
        ):
            self._activate_model(candidate)

    def _training_rows(
        self,
        *,
        mode: RiskMode | None = None,
        configuration_fingerprint: str | None = None,
        match_configuration: bool = False,
    ) -> list[tuple[LearningObservation, float]]:
        rows: list[tuple[LearningObservation, float]] = []
        key = str(PRIMARY_HORIZON_SECONDS)
        for observation in sorted(self.observations.values(), key=lambda item: item.created_at):
            if mode is not None and observation.risk_mode != mode:
                continue
            if match_configuration and (
                observation.configuration_fingerprint != configuration_fingerprint
            ):
                continue
            checkpoint = observation.checkpoints.get(key)
            if (
                checkpoint is not None
                and checkpoint.net_return is not None
                and _observation_features_complete(observation)
            ):
                rows.append((observation, checkpoint.net_return))
        return rows

    def _retrain_if_ready(self) -> None:
        self._govern_active_model()
        all_rows = self._training_rows()
        self.outcomes_seen = max(self.outcomes_seen, len(all_rows))
        if not all_rows:
            return
        target_mode = all_rows[-1][0].risk_mode
        target_configuration = all_rows[-1][0].configuration_fingerprint
        key = str(PRIMARY_HORIZON_SECONDS)
        resolved = [
            observation
            for observation in sorted(self.observations.values(), key=lambda item: item.created_at)
            if observation.risk_mode == target_mode
            and observation.configuration_fingerprint == target_configuration
            and _observation_features_complete(observation)
            and key in observation.checkpoints
        ][-MODEL_WINDOW_OBSERVATIONS:]
        rows: list[tuple[LearningObservation, float]] = []
        for observation in resolved:
            outcome = observation.checkpoints[key].net_return
            if outcome is not None:
                rows.append((observation, outcome))
        if len(rows) < MINIMUM_TRAINING_SAMPLES:
            return
        latest = self._latest_model_for_context(target_mode, target_configuration)
        if (
            latest is not None
            and self.outcomes_seen - latest.outcomes_seen < RETRAIN_SAMPLE_INTERVAL
        ):
            return
        validation_count = max(MINIMUM_VALIDATION_SAMPLES, len(rows) // 3)
        raw_training = rows[:-validation_count]
        validation = rows[-validation_count:]
        validation_start = validation[0][0].created_at
        training = [
            row
            for row in raw_training
            if row[0].checkpoints[str(PRIMARY_HORIZON_SECONDS)].observed_at <= validation_start
        ]
        if len(training) < MINIMUM_FIT_SAMPLES:
            return
        candidate = _fit(training)
        if candidate is None:
            return
        predictions = [_predict_parts(candidate, item.features) for item, _ in validation]
        outcomes = [outcome for _, outcome in validation]
        baseline_predictions = [item.baseline_edge_index for item, _ in validation]
        training_mean = fmean(outcome for _, outcome in training)
        learner_rmse = _rmse(predictions, outcomes)
        naive_rmse = _rmse([training_mean] * len(outcomes), outcomes)
        learner_correlation = _correlation(predictions, outcomes)
        baseline_correlation = _correlation(baseline_predictions, outcomes)
        learner_top_mean = _top_mean(predictions, outcomes)
        baseline_top_mean = _top_mean(baseline_predictions, outcomes)
        outcome_availability = len(rows) / len(resolved)
        in_distribution = [
            _within_parts_support(candidate, item.features) for item, _ in validation
        ]
        in_distribution_fraction = sum(in_distribution) / len(in_distribution)
        policy_rows = [
            (item, outcome, prediction, supported)
            for (item, outcome), prediction, supported in zip(
                validation,
                predictions,
                in_distribution,
                strict=True,
            )
            if item.baseline_action == DecisionAction.ENTER and item.baseline_actionable
        ]
        policy_support = [
            supported and prediction - learner_rmse > 0
            for _, _, prediction, supported in policy_rows
        ]
        policy_deltas = [
            0.0 if support else -outcome
            for (_, outcome, _, _), support in zip(policy_rows, policy_support, strict=True)
        ]
        policy_mean_uplift = fmean(policy_deltas) if policy_deltas else None
        policy_uplift_lower = _mean_lower_bound(
            policy_deltas,
            z_score=ENTRY_POLICY_Z_SCORE,
        )
        policy_veto_count = len(policy_support) - sum(policy_support)
        policy_winner_veto_count = sum(
            not support and outcome > 0
            for (_, outcome, _, _), support in zip(policy_rows, policy_support, strict=True)
        )
        qualified = bool(
            outcome_availability >= ENTRY_MINIMUM_OUTCOME_AVAILABILITY
            and learner_rmse <= naive_rmse * (1 - ENTRY_MINIMUM_RMSE_RELATIVE_IMPROVEMENT)
            and learner_correlation >= max(0.10, baseline_correlation + 0.03)
            and learner_top_mean >= ENTRY_MINIMUM_TOP_RETURN
            and learner_top_mean >= baseline_top_mean + ENTRY_MINIMUM_TOP_UPLIFT
            and in_distribution_fraction >= ENTRY_MINIMUM_IN_DISTRIBUTION_FRACTION
            and len(policy_rows) >= ENTRY_MINIMUM_POLICY_SAMPLES
            and policy_veto_count >= ENTRY_MINIMUM_POLICY_VETOES
            and policy_uplift_lower is not None
            and policy_uplift_lower > ENTRY_MINIMUM_POLICY_UPLIFT
        )
        # Persist the exact coefficients evaluated above. Re-fitting on validation data would
        # deploy a different artifact than the one that actually earned qualification.
        means, scales, coefficients = candidate
        model = LearningModel(
            version=(
                f"{LEARNER_VERSION_PREFIX}{target_mode.value}-"
                f"{target_configuration or 'default'}-{self.outcomes_seen}-"
                f"{int(datetime.now(UTC).timestamp())}"
            ),
            outcomes_seen=self.outcomes_seen,
            risk_mode=target_mode,
            configuration_fingerprint=target_configuration,
            sample_count=len(rows),
            resolved_count=len(resolved),
            outcome_availability_fraction=outcome_availability,
            training_count=len(training),
            validation_count=len(validation),
            embargoed_count=len(raw_training) - len(training),
            feature_names=list(FEATURE_NAMES),
            means=means,
            scales=scales,
            coefficients=coefficients,
            validation_rmse=learner_rmse,
            naive_rmse=naive_rmse,
            learner_correlation=learner_correlation,
            baseline_correlation=baseline_correlation,
            learner_top_mean_return=learner_top_mean,
            baseline_top_mean_return=baseline_top_mean,
            overall_mean_return=fmean(outcome for _, outcome in rows),
            validation_in_distribution_fraction=in_distribution_fraction,
            policy_validation_count=len(policy_rows),
            policy_veto_count=policy_veto_count,
            policy_winner_veto_count=policy_winner_veto_count,
            policy_mean_uplift=policy_mean_uplift,
            policy_uplift_lower_bound=policy_uplift_lower,
            qualified=qualified,
        )
        self.models.append(model)
        self.database.save_learning_model(model)
        self._prune_model_history()
        self._govern_active_model()

    def _record_usable_outcome(self) -> None:
        self.outcomes_seen += 1
        self.database.set_setting("learning_outcomes_seen", self.outcomes_seen)

    def _prune_complete_history(self) -> None:
        removed = False
        for mint in self.database.prune_learning_observations(MAX_COMPLETED_OBSERVATIONS):
            self.observations.pop(mint, None)
            removed = True
        if removed:
            self._invalidate_timing_validation()

    def _prune_model_history(self) -> None:
        protected = set(self.disabled_model_versions)
        if self.active_model is not None:
            protected.add(self.active_model.version)
        removed = set(
            self.database.prune_learning_models(
                MAX_MODEL_VERSIONS,
                preserve_versions=protected,
            )
        )
        if removed:
            self.models = [model for model in self.models if model.version not in removed]

    def _invalidate_timing_validation(self) -> None:
        self._timing_revision += 1
        self._timing_cache.clear()


def _checkpoint_utility(observation: LearningObservation, horizon: int) -> float:
    """Decision utility only: an unavailable exit is worst-case, never reported as P/L."""

    checkpoint = observation.checkpoints.get(str(horizon))
    return (
        checkpoint.net_return
        if checkpoint is not None and checkpoint.net_return is not None
        else -1.0
    )


def _mean_horizon_utility(observations: list[LearningObservation], horizon: int) -> float:
    """Mean decision utility for a comparable set of point-in-time observations."""

    if not observations:
        return -1.0
    return fmean(_checkpoint_utility(observation, horizon) for observation in observations)


def _mean_lower_bound(values: list[float], *, z_score: float) -> float | None:
    if not values:
        return None
    mean = fmean(values)
    if len(values) < 2:
        return mean
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean - z_score * math.sqrt(variance / len(values))


def _feature_vector(decision: Decision) -> dict[str, float] | None:
    values = decision.feature_snapshot
    integrity: dict[str, float] = {}
    for name in INTEGRITY_FEATURE_NAMES:
        item = values.values.get(name)
        if (
            item is None
            or item.value is None
            or isinstance(item.value, bool)
            or item.missing_reason is not None
        ):
            return None
        try:
            number = float(item.value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        integrity[name] = _clamp(number)
    reserve_sol = max(0.0, values.number("virtual_quote_reserve_sol"))
    return {
        "opportunity": decision.score.opportunity,
        "danger": decision.score.danger,
        "execution": decision.score.execution,
        "confidence": decision.score.confidence,
        "buy_ratio": _clamp(values.number("buy_ratio_5m")),
        "wallet_breadth": _clamp(values.number("unique_wallets_5m") / 30),
        "concentration": _clamp(values.number("wallet_volume_hhi", 1.0)),
        "repetition": _clamp(values.number("repeated_amount_ratio")),
        "coordination": _clamp(values.number("same_slot_ratio")),
        "curve_progress": _clamp(values.number("curve_progress")),
        "momentum": max(-1.0, min(1.0, values.number("momentum_1m"))),
        "drawdown": _clamp(values.number("drawdown_5m")),
        "reserve_depth": _clamp(math.log1p(reserve_sol) / math.log(1_001)),
        **integrity,
    }


def _observation_features_complete(observation: LearningObservation) -> bool:
    return all(
        name in observation.features and math.isfinite(observation.features[name])
        for name in FEATURE_NAMES
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _fit(
    rows: list[tuple[LearningObservation, float]],
) -> tuple[list[float], list[float], list[float]] | None:
    if not rows:
        return None
    raw = [[item.features.get(name, 0.0) for name in FEATURE_NAMES] for item, _ in rows]
    outcomes = [max(-1.0, min(3.0, outcome)) for _, outcome in rows]
    weights = [0.5 ** ((len(rows) - 1 - index) / 500) for index in range(len(rows))]
    weight_sum = sum(weights)
    means = [
        sum(weight * row[index] for weight, row in zip(weights, raw, strict=True)) / weight_sum
        for index in range(len(FEATURE_NAMES))
    ]
    scales = []
    for index, mean in enumerate(means):
        variance = (
            sum(weight * (row[index] - mean) ** 2 for weight, row in zip(weights, raw, strict=True))
            / weight_sum
        )
        # A nearly constant historical feature should not make a harmless one-basis-point
        # variation look infinitely far out of distribution. The features are normalized to
        # roughly [-1, 1], so this still makes a six-percentage-point move the minimum support
        # envelope while genuinely unfamiliar combinations fall back to the baseline.
        scales.append(max(MINIMUM_FEATURE_SCALE, math.sqrt(variance)))
    design = [
        [
            1.0,
            *[
                (value - mean) / scale
                for value, mean, scale in zip(row, means, scales, strict=True)
            ],
        ]
        for row in raw
    ]
    width = len(FEATURE_NAMES) + 1
    matrix = [[0.0] * width for _ in range(width)]
    target = [0.0] * width
    for weight, row, outcome in zip(weights, design, outcomes, strict=True):
        for left in range(width):
            target[left] += weight * row[left] * outcome
            for right in range(width):
                matrix[left][right] += weight * row[left] * row[right]
    matrix[0][0] += 1e-6
    for index in range(1, width):
        matrix[index][index] += 2.0
    coefficients = _solve(matrix, target)
    return (means, scales, coefficients) if coefficients is not None else None


def _solve(matrix: list[list[float]], target: list[float]) -> list[float] | None:
    size = len(target)
    augmented = [row[:] + [target[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0:
                continue
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[index][-1] for index in range(size)]


def _predict(model: LearningModel, features: dict[str, float]) -> float:
    return _predict_parts((model.means, model.scales, model.coefficients), features)


def _within_model_support(model: LearningModel, features: dict[str, float]) -> bool:
    if not _model_shape_valid(model):
        return False
    return _within_parts_support((model.means, model.scales, model.coefficients), features)


def _model_shape_valid(model: LearningModel) -> bool:
    width = len(FEATURE_NAMES)
    return bool(
        model.feature_names == list(FEATURE_NAMES)
        and len(model.means) == width
        and len(model.scales) == width
        and len(model.coefficients) == width + 1
        and all(math.isfinite(value) for value in model.means)
        and all(math.isfinite(value) and value > 0 for value in model.scales)
        and all(math.isfinite(value) for value in model.coefficients)
    )


def _within_parts_support(
    model: tuple[list[float], list[float], list[float]],
    features: dict[str, float],
) -> bool:
    means, scales, _ = model
    if (
        len(means) != len(FEATURE_NAMES)
        or len(scales) != len(FEATURE_NAMES)
        or any(not math.isfinite(value) for value in means)
        or any(not math.isfinite(value) or value <= 0 for value in scales)
    ):
        return False
    return all(
        abs((features.get(name, 0.0) - mean) / max(scale, 1e-6)) <= MODEL_SUPPORT_Z_SCORE
        for name, mean, scale in zip(FEATURE_NAMES, means, scales, strict=True)
    )


def _predict_parts(
    model: tuple[list[float], list[float], list[float]],
    features: dict[str, float],
) -> float:
    means, scales, coefficients = model
    prediction = coefficients[0]
    for index, name in enumerate(FEATURE_NAMES):
        prediction += coefficients[index + 1] * (
            (features.get(name, 0.0) - means[index]) / scales[index]
        )
    return max(-1.0, min(10.0, prediction))


def _rmse(predictions: list[float], outcomes: list[float]) -> float:
    return math.sqrt(
        fmean(
            (prediction - outcome) ** 2
            for prediction, outcome in zip(predictions, outcomes, strict=True)
        )
    )


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2:
        return 0.0
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_sum * right_sum)
    return 0.0 if denominator <= 0 else max(-1.0, min(1.0, numerator / denominator))


def _top_mean(predictions: list[float], outcomes: list[float]) -> float:
    count = max(1, len(outcomes) // 3)
    ranked = sorted(zip(predictions, outcomes, strict=True), reverse=True)
    return fmean(outcome for _, outcome in ranked[:count])


def _model_summary(model: LearningModel | None) -> dict[str, Any] | None:
    if model is None:
        return None
    return {
        "version": model.version,
        "created_at": model.created_at.isoformat(),
        "outcomes_seen": model.outcomes_seen,
        "risk_mode": model.risk_mode.value if model.risk_mode is not None else None,
        "configuration_fingerprint": model.configuration_fingerprint,
        "sample_count": model.sample_count,
        "resolved_count": model.resolved_count,
        "outcome_availability_fraction": model.outcome_availability_fraction,
        "training_count": model.training_count,
        "validation_count": model.validation_count,
        "embargoed_count": model.embargoed_count,
        "validation_rmse": model.validation_rmse,
        "naive_rmse": model.naive_rmse,
        "learner_correlation": model.learner_correlation,
        "baseline_correlation": model.baseline_correlation,
        "learner_top_mean_return": model.learner_top_mean_return,
        "baseline_top_mean_return": model.baseline_top_mean_return,
        "overall_mean_return": model.overall_mean_return,
        "validation_in_distribution_fraction": model.validation_in_distribution_fraction,
        "policy_validation_count": model.policy_validation_count,
        "policy_veto_count": model.policy_veto_count,
        "policy_winner_veto_count": model.policy_winner_veto_count,
        "policy_mean_uplift": model.policy_mean_uplift,
        "policy_uplift_lower_bound": model.policy_uplift_lower_bound,
        "qualified": model.qualified,
    }


def _entry_qualification_gates(
    model: LearningModel | None,
    *,
    usable_outcomes: int,
    current_availability: dict[str, Any],
    activation_available: bool,
) -> list[dict[str, Any]]:
    """Describe existing learner gates without making the UI reimplement policy."""

    def gate(
        gate_id: str,
        label: str,
        current: float | int | bool | None,
        target: float | int | bool,
        comparison: str,
        passed: bool,
        unit: str,
        detail: str,
    ) -> dict[str, Any]:
        return {
            "id": gate_id,
            "label": label,
            "current": current,
            "target": target,
            "comparison": comparison,
            "state": "passed" if passed else "collecting" if current is None else "not_met",
            "unit": unit,
            "detail": detail,
        }

    gates = [
        gate(
            "usable_outcomes",
            "Usable outcomes",
            usable_outcomes,
            MINIMUM_TRAINING_SAMPLES,
            ">=",
            usable_outcomes >= MINIMUM_TRAINING_SAMPLES,
            "count",
            "Fee-inclusive five-minute outcomes available for the current risk and provider setup.",
        )
    ]
    if model is None:
        pending = (
            (
                "model_outcome_availability",
                "Model outcome coverage",
                ENTRY_MINIMUM_OUTCOME_AVAILABILITY,
                "fraction",
            ),
            ("validation_error", "Validation error", 0.0, "number"),
            ("rank_fit", "Forward rank fit", 0.0, "number"),
            ("top_return", "Top-group return", ENTRY_MINIMUM_TOP_RETURN, "fraction"),
            ("top_uplift", "Top-group uplift", ENTRY_MINIMUM_TOP_UPLIFT, "fraction"),
            (
                "in_distribution",
                "Familiar evidence",
                ENTRY_MINIMUM_IN_DISTRIBUTION_FRACTION,
                "fraction",
            ),
            ("policy_samples", "Actionable policy outcomes", ENTRY_MINIMUM_POLICY_SAMPLES, "count"),
            ("policy_vetoes", "Tested vetoes", ENTRY_MINIMUM_POLICY_VETOES, "count"),
            (
                "policy_uplift_floor",
                "Conservative veto value",
                ENTRY_MINIMUM_POLICY_UPLIFT,
                "fraction",
            ),
        )
        gates.extend(
            gate(
                gate_id,
                label,
                None,
                target,
                (
                    "<="
                    if gate_id == "validation_error"
                    else ">"
                    if gate_id == "policy_uplift_floor"
                    else ">="
                ),
                False,
                unit,
                "Available after the first chronological challenger is fitted.",
            )
            for gate_id, label, target, unit in pending
        )
    else:
        error_target = model.naive_rmse * (1 - ENTRY_MINIMUM_RMSE_RELATIVE_IMPROVEMENT)
        rank_target = max(0.10, model.baseline_correlation + 0.03)
        top_uplift = model.learner_top_mean_return - model.baseline_top_mean_return
        gates.extend(
            [
                gate(
                    "model_outcome_availability",
                    "Model outcome coverage",
                    model.outcome_availability_fraction,
                    ENTRY_MINIMUM_OUTCOME_AVAILABILITY,
                    ">=",
                    model.outcome_availability_fraction >= ENTRY_MINIMUM_OUTCOME_AVAILABILITY,
                    "fraction",
                    "Enough modeled entries had executable, fee-inclusive outcomes.",
                ),
                gate(
                    "validation_error",
                    "Validation error",
                    model.validation_rmse,
                    error_target,
                    "<=",
                    model.validation_rmse <= error_target,
                    "number",
                    "The challenger must beat the untouched naive forecast by at least 2%.",
                ),
                gate(
                    "rank_fit",
                    "Forward rank fit",
                    model.learner_correlation,
                    rank_target,
                    ">=",
                    model.learner_correlation >= rank_target,
                    "number",
                    "Forward ranking must be useful and improve on the Baseline association.",
                ),
                gate(
                    "top_return",
                    "Top-group return",
                    model.learner_top_mean_return,
                    ENTRY_MINIMUM_TOP_RETURN,
                    ">=",
                    model.learner_top_mean_return >= ENTRY_MINIMUM_TOP_RETURN,
                    "fraction",
                    "The highest-ranked untouched group must remain positive after costs.",
                ),
                gate(
                    "top_uplift",
                    "Top-group uplift",
                    top_uplift,
                    ENTRY_MINIMUM_TOP_UPLIFT,
                    ">=",
                    top_uplift >= ENTRY_MINIMUM_TOP_UPLIFT,
                    "fraction",
                    "The challenger top group must improve on the Baseline top group.",
                ),
                gate(
                    "in_distribution",
                    "Familiar evidence",
                    model.validation_in_distribution_fraction,
                    ENTRY_MINIMUM_IN_DISTRIBUTION_FRACTION,
                    ">=",
                    model.validation_in_distribution_fraction
                    >= ENTRY_MINIMUM_IN_DISTRIBUTION_FRACTION,
                    "fraction",
                    "Almost all validation evidence must remain inside learned support.",
                ),
                gate(
                    "policy_samples",
                    "Actionable policy outcomes",
                    model.policy_validation_count,
                    ENTRY_MINIMUM_POLICY_SAMPLES,
                    ">=",
                    model.policy_validation_count >= ENTRY_MINIMUM_POLICY_SAMPLES,
                    "count",
                    "Only Baseline entries that could really have acted count toward veto proof.",
                ),
                gate(
                    "policy_vetoes",
                    "Tested vetoes",
                    model.policy_veto_count,
                    ENTRY_MINIMUM_POLICY_VETOES,
                    ">=",
                    model.policy_veto_count >= ENTRY_MINIMUM_POLICY_VETOES,
                    "count",
                    "The proposed protection must be exercised often enough to judge.",
                ),
                gate(
                    "policy_uplift_floor",
                    "Conservative veto value",
                    model.policy_uplift_lower_bound,
                    ENTRY_MINIMUM_POLICY_UPLIFT,
                    ">",
                    model.policy_uplift_lower_bound is not None
                    and model.policy_uplift_lower_bound > ENTRY_MINIMUM_POLICY_UPLIFT,
                    "fraction",
                    "The confidence-adjusted value of the tested veto policy must be positive.",
                ),
            ]
        )
    gates.append(
        gate(
            "current_outcome_availability",
            "Current executable coverage",
            float(current_availability["availability_fraction"]),
            float(current_availability["minimum_fraction"]),
            ">=",
            float(current_availability["availability_fraction"])
            >= float(current_availability["minimum_fraction"]),
            "fraction",
            "Recent evidence must still be observable when the user chooses to activate.",
        )
    )
    gates.append(
        gate(
            "current_observed_outcomes",
            "Current coverage sample",
            int(current_availability["observed_count"]),
            MINIMUM_TRAINING_SAMPLES,
            ">=",
            int(current_availability["observed_count"]) >= MINIMUM_TRAINING_SAMPLES,
            "count",
            "Coverage needs a full recent sample before it can support activation.",
        )
    )
    gates.append(
        gate(
            "activation_ready",
            "Final safety approval",
            activation_available,
            True,
            "=",
            activation_available,
            "boolean",
            "The newest artifact, context, suspension history, and all proof gates agree.",
        )
    )
    return gates


def _lessons(model: LearningModel | None) -> list[dict[str, Any]]:
    if model is None or len(model.coefficients) != len(model.feature_names) + 1:
        return []
    ranked = sorted(
        zip(model.feature_names, model.coefficients[1:], strict=True),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    return [
        {
            "feature": feature,
            "label": FEATURE_LABELS.get(feature, feature.replace("_", " ")),
            "effect": "helped" if coefficient > 0 else "hurt",
            "coefficient": coefficient,
        }
        for feature, coefficient in ranked[:5]
    ]
