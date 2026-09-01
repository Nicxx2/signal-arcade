from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from datetime import UTC, datetime
from statistics import fmean
from typing import Any, Literal

from ..config import Settings
from ..database import Database
from ..models import (
    RISK_LIMITS,
    ChallengerChampionEvent,
    ChallengerEvaluationReceipt,
    ChallengerSizeTrial,
    ChallengerSkill,
    ChallengerSkillArtifact,
    ChallengerSkillState,
    CoachExperimentKind,
    CoachExperimentState,
    CoachHypothesis,
    Decision,
    DecisionAction,
    LearningAssessment,
    LearningCheckpoint,
    LearningMode,
    LearningModel,
    LearningObservation,
    LearningObservationStatus,
    MarketIntegrityState,
    RiskMode,
)
from ..paper.curve_math import quote_buy, quote_sell
from ..strategy import BASELINE_VERSION, LEARNABLE_BASELINE_VERSIONS
from .features import NATIVE_SOL_MINT, WRAPPED_SOL_MINT, TokenState

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
MAX_CLOCK_CHECKPOINTS_PER_TICK = 20
LEARNER_VERSION_PREFIX = "learner-v4-"
SKILL_ARTIFACT_VERSION_PREFIX = "challenger-skill-v1-"
FEATURE_SCHEMA_VERSION = "challenger-features-v3"
TOURNAMENT_MINIMUM_COMMON_OUTCOMES = 30
TOURNAMENT_MAXIMUM_COMMON_OUTCOMES = 120
TOURNAMENT_MINIMUM_AVAILABILITY = 0.70
TOURNAMENT_MAXIMUM_COMMON_OBSERVED = math.ceil(
    TOURNAMENT_MAXIMUM_COMMON_OUTCOMES / TOURNAMENT_MINIMUM_AVAILABILITY
)
TOURNAMENT_Z_SCORE = 1.96
MAX_CHAMPION_JOURNEY_EVENTS = 12
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
    "microtrade_count_ratio",
    "meaningful_volume_ratio",
    "meaningful_wallet_ratio",
    "median_trade_quote_sol",
    "price_path_efficiency",
    "rapid_price_reversal_ratio",
    "trade_density_5m",
)
MANIPULATION_FEATURE_NAMES = (
    "danger",
    "confidence",
    "concentration",
    "repetition",
    "coordination",
    *INTEGRITY_FEATURE_NAMES,
)


def _coach_outcome_context_key(
    risk_mode: RiskMode,
    configuration_fingerprint: str | None,
    baseline_version: str,
    feature_schema_version: str,
    dependency_versions: dict[str, str],
) -> str:
    dependencies = ",".join(
        f"{skill}:{version}" for skill, version in sorted(dependency_versions.items())
    )
    material = "\n".join(
        (
            risk_mode.value,
            configuration_fingerprint or "",
            baseline_version,
            feature_schema_version,
            dependencies,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


MANIPULATION_MINIMUM_IN_DISTRIBUTION_FRACTION = 0.90
MANIPULATION_MAXIMUM_WINNER_VETO_FRACTION = 0.35
SIZING_FEATURE_NAMES = (
    "opportunity",
    "danger",
    "execution",
    "confidence",
    "reserve_depth",
    "momentum",
    "drawdown",
    *INTEGRITY_FEATURE_NAMES,
)
SIZING_MULTIPLIERS = (0.5, 1.0, 1.5, 2.0)
CoachOperator = Literal["<=", ">="]
COACH_ENTRY_RULES: tuple[tuple[str, CoachOperator, float], ...] = (
    ("momentum", "<=", -0.05),
    ("momentum", "<=", 0.00),
    ("buy_ratio", "<=", 0.50),
    ("buy_ratio", "<=", 0.55),
    ("drawdown", ">=", 0.18),
    ("drawdown", ">=", 0.30),
    ("execution", "<=", 0.85),
    ("confidence", "<=", 0.72),
)
COACH_MANIPULATION_RULES: tuple[tuple[str, CoachOperator, float], ...] = (
    ("concentration", ">=", 0.35),
    ("concentration", ">=", 0.50),
    ("danger", ">=", 0.20),
    ("danger", ">=", 0.30),
    ("single_trade_wallet_ratio", ">=", 0.90),
    ("round_trip_wallet_ratio", ">=", 0.35),
    ("round_trip_volume_ratio", ">=", 0.50),
    ("net_quote_flow_ratio", "<=", 0.20),
    ("side_alternation_ratio", ">=", 0.75),
    ("quantized_amount_repeat_ratio", ">=", 0.40),
    ("slot_concentration_hhi", ">=", 0.30),
    ("price_direction_consistency", ">=", 0.90),
    ("microtrade_count_ratio", ">=", 0.75),
    ("microtrade_count_ratio", ">=", 0.90),
    ("meaningful_volume_ratio", "<=", 0.35),
    ("meaningful_wallet_ratio", "<=", 0.35),
    ("median_trade_quote_sol", "<=", 0.005),
    ("price_path_efficiency", "<=", 0.15),
    ("rapid_price_reversal_ratio", ">=", 0.60),
    ("trade_density_5m", ">=", 0.70),
)
COACH_MANIPULATION_COMBINATIONS: tuple[
    tuple[tuple[str, CoachOperator, float], tuple[str, CoachOperator, float]], ...
] = (
    (
        ("round_trip_volume_ratio", ">=", 0.50),
        ("net_quote_flow_ratio", "<=", 0.20),
    ),
    (
        ("side_alternation_ratio", ">=", 0.75),
        ("quantized_amount_repeat_ratio", ">=", 0.40),
    ),
    (
        ("single_trade_wallet_ratio", ">=", 0.90),
        ("slot_concentration_hhi", ">=", 0.30),
    ),
    (
        ("price_direction_consistency", ">=", 0.90),
        ("net_quote_flow_ratio", "<=", 0.20),
    ),
    (
        ("microtrade_count_ratio", ">=", 0.75),
        ("meaningful_volume_ratio", "<=", 0.35),
    ),
    (
        ("meaningful_wallet_ratio", "<=", 0.35),
        ("median_trade_quote_sol", "<=", 0.005),
    ),
    (
        ("price_path_efficiency", "<=", 0.15),
        ("rapid_price_reversal_ratio", ">=", 0.60),
    ),
)
SIZING_MINIMUM_POLICY_CHANGES = 5
SIZING_MAXIMUM_HARM_FRACTION = 0.35
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
    "microtrade_count_ratio": "dust-sized trade share",
    "meaningful_volume_ratio": "economically meaningful volume share",
    "meaningful_wallet_ratio": "economically meaningful wallet share",
    "median_trade_quote_sol": "median trade size",
    "price_path_efficiency": "price-path efficiency",
    "rapid_price_reversal_ratio": "rapid price reversals",
    "trade_density_5m": "five-minute trade density",
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


def _checkpoint_route_missing_reason(
    state: TokenState,
    now: datetime,
    *,
    stale_after_seconds: int,
    require_timestamp: bool,
) -> str | None:
    """Return a stable diagnostic when a cached state cannot support an executable exit quote."""

    if state.virtual_token_reserves <= 0 or state.virtual_quote_reserves <= 0:
        return "route_reserves_unavailable"
    if state.complete and state.venue == "pump_curve":
        return "migration_route_unconfirmed"
    if state.venue == "pump_swap" and not state.route_verified:
        return "pumpswap_route_unverified"
    if state.quote_mint not in {WRAPPED_SOL_MINT, NATIVE_SOL_MINT}:
        return "unsupported_quote_route"
    observed_at = state.last_reserve_at or state.last_event_at
    if observed_at is None:
        return "reserve_timestamp_unavailable" if require_timestamp else None
    if observed_at > now:
        return "future_route_timestamp"
    if (now - observed_at).total_seconds() > stale_after_seconds:
        return "stale_cached_route"
    return None


def _expired_checkpoint_reason(
    state: TokenState | None,
    now: datetime,
    *,
    stale_after_seconds: int,
) -> str:
    if state is None:
        return "tracked_route_state_unavailable"
    return (
        _checkpoint_route_missing_reason(
            state,
            now,
            stale_after_seconds=stale_after_seconds,
            require_timestamp=True,
        )
        or "checkpoint_window_elapsed"
    )


class LearningEngine:
    """Local, versioned challenger trained only on forward live-paper outcomes."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        configuration_fingerprint: Callable[[], str | None] | None = None,
        baseline_version: Callable[[], str] | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.configuration_fingerprint = configuration_fingerprint or (lambda: None)
        # A locked predecessor season must finish on its own strategy generation after an
        # upgrade. Keeping the active Baseline callback beside the configuration fingerprint lets
        # its Challenger cohort continue honestly until the next season adopts the new policy.
        self.baseline_version = baseline_version or (lambda: BASELINE_VERSION)
        try:
            self.current_risk_mode = RiskMode(
                database.get_setting("risk_mode", RiskMode.BALANCED.value)
            )
        except ValueError:
            self.current_risk_mode = RiskMode.BALANCED
        self.observations = {item.mint: item for item in database.list_learning_observations()}
        self.models = database.list_learning_models()
        self.skill_artifacts = {
            artifact.version: artifact for artifact in database.list_challenger_artifacts()
        }
        self.skill_states = {
            (state.cohort_key, state.skill): state
            for state in database.list_challenger_skill_states()
        }
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
        stored_context_counts = database.get_setting("learning_context_outcomes_seen", {})
        self.context_outcome_counts = (
            {
                str(key): max(0, int(value))
                for key, value in stored_context_counts.items()
                if isinstance(key, str) and isinstance(value, int | float)
            }
            if isinstance(stored_context_counts, dict)
            else {}
        )
        retained_context_counts: dict[str, int] = {}
        primary_key = str(PRIMARY_HORIZON_SECONDS)
        for observation in self.observations.values():
            checkpoint = observation.checkpoints.get(primary_key)
            if checkpoint is None or checkpoint.net_return is None:
                continue
            context_key = _coach_outcome_context_key(
                observation.risk_mode,
                observation.configuration_fingerprint,
                observation.baseline_version,
                observation.feature_schema_version,
                observation.active_skill_versions,
            )
            retained_context_counts[context_key] = retained_context_counts.get(context_key, 0) + 1
        for context_key, count in retained_context_counts.items():
            self.context_outcome_counts[context_key] = max(
                count,
                self.context_outcome_counts.get(context_key, 0),
            )
        database.set_setting("learning_context_outcomes_seen", self.context_outcome_counts)
        try:
            self.mode = LearningMode(
                database.get_setting("learning_mode", LearningMode.SHADOW.value)
            )
        except ValueError:
            self.mode = LearningMode.SHADOW
            database.set_setting("learning_mode", self.mode.value)
        self.consent_granted = bool(
            database.get_setting("challenger_consent_granted", self.mode == LearningMode.ACTIVE)
        )
        saved_active_skills = database.get_setting("active_challenger_skills", {})
        self.active_skill_versions = (
            {
                str(skill): str(version)
                for skill, version in saved_active_skills.items()
                if isinstance(skill, str) and isinstance(version, str)
            }
            if isinstance(saved_active_skills, dict)
            else {}
        )
        self._restore_active_skill_versions()
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
        elif self.active_model is None and not self.active_skill_versions:
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

        risk_mode_changed = self.current_risk_mode != mode
        self.current_risk_mode = mode
        if self.mode == LearningMode.ACTIVE and (
            (self.active_model is not None and self.active_model.risk_mode != mode)
            or (risk_mode_changed and bool(self.active_skill_versions))
        ):
            self.set_mode(LearningMode.SHADOW)

    def configuration_changed(self) -> None:
        """A new fee/provider/latency policy invalidates an active artifact's provenance."""

        self._invalidate_timing_validation()
        if self.mode == LearningMode.ACTIVE and (
            (
                self.active_model is not None
                and self.active_model.configuration_fingerprint != self.configuration_fingerprint()
            )
            or bool(self.active_skill_versions)
        ):
            self.set_mode(LearningMode.SHADOW)

    def set_mode(self, mode: LearningMode) -> None:
        if mode == LearningMode.ACTIVE:
            skill_candidate = self._skill_activation_candidate()
            if skill_candidate is not None:
                self.active_model = None
                self.database.set_setting("active_learning_model", "")
                self.consent_granted = True
                self.database.set_setting("challenger_consent_granted", True)
                self._activate_skill(skill_candidate)
                self.mode = mode
                self.database.set_setting("learning_mode", mode.value)
                return
            candidate = self._activation_candidate()
            if candidate is None:
                raise ValueError(
                    "the newest challenger must pass the current forward and suspension gates "
                    "before activation"
                )
            self._activate_model(candidate)
            self.consent_granted = True
            self.database.set_setting("challenger_consent_granted", True)
        elif self.mode == LearningMode.ACTIVE:
            self.active_model = None
            self.database.set_setting("active_learning_model", "")
            self._deactivate_all_skills()
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
        size_trials = self._build_size_trials(
            state,
            base_size_sol=size_sol,
            fee_bps=fee_bps,
            risk_mode=decision.risk_mode,
            baseline_entry=entry,
        )
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
            baseline_version=decision.model_version.split("+", maxsplit=1)[0],
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            size_trials=size_trials,
            active_skill_versions=dict(self.active_skill_versions),
        )
        self._freeze_skill_evaluations(observation)
        self.observations[state.mint] = observation
        self.database.save_learning_observation(observation)
        return True

    def _build_size_trials(
        self,
        state: TokenState,
        *,
        base_size_sol: float,
        fee_bps: int,
        risk_mode: RiskMode,
        baseline_entry: Any,
    ) -> dict[str, ChallengerSizeTrial]:
        trials: dict[str, ChallengerSizeTrial] = {}
        network_fee = self.settings.network_fee_lamports + self.settings.priority_fee_lamports
        for multiplier in SIZING_MULTIPLIERS:
            key = _size_trial_key(multiplier)
            budget = max(1, int(base_size_sol * multiplier * 1_000_000_000))
            try:
                quote = (
                    baseline_entry
                    if multiplier == 1.0
                    else quote_buy(
                        virtual_token_reserves=state.virtual_token_reserves,
                        virtual_sol_reserves=state.virtual_quote_reserves,
                        real_token_reserves=state.real_token_reserves,
                        wallet_trade_budget_lamports=budget,
                        fee_bps=fee_bps,
                        network_fee_lamports=network_fee,
                    )
                )
                eligible = bool(
                    quote.price_impact_fraction <= RISK_LIMITS[risk_mode].max_price_impact
                )
                trials[key] = ChallengerSizeTrial(
                    multiplier=multiplier,
                    budget_lamports=budget,
                    token_units=quote.token_units,
                    entry_cost_lamports=quote.wallet_sol_lamports,
                    entry_price_impact_fraction=quote.price_impact_fraction,
                    eligible_at_entry=eligible,
                    entry_missing_reason=None if eligible else "entry_impact_above_mode_limit",
                )
            except ValueError:
                trials[key] = ChallengerSizeTrial(
                    multiplier=multiplier,
                    budget_lamports=budget,
                    entry_missing_reason="entry_quote_unavailable",
                )
        return trials

    def observe_market(
        self,
        state: TokenState,
        now: datetime,
        *,
        live: bool,
        cached: bool = False,
    ) -> int:
        if not live:
            return 0
        observation = self.observations.get(state.mint)
        if observation is None or observation.status != LearningObservationStatus.PENDING:
            return 0
        age = max(0.0, (now - observation.created_at).total_seconds())
        changed = 0
        primary_checkpoint_changed = False
        primary_became_available = False
        route_missing = _checkpoint_route_missing_reason(
            state,
            now,
            stale_after_seconds=self.settings.stale_market_seconds,
            require_timestamp=cached,
        )
        for horizon in LEARNING_HORIZONS_SECONDS:
            key = str(horizon)
            if key in observation.checkpoints or age < horizon:
                continue
            observation.checkpoint_attempts[key] = observation.checkpoint_attempts.get(key, 0) + 1
            if age > horizon + CHECKPOINT_GRACE_SECONDS:
                missing_reason = route_missing or "checkpoint_window_elapsed"
                observation.checkpoints[key] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=now,
                    missing_reason=missing_reason,
                )
                self._mark_size_trials_missing(observation, horizon, now, missing_reason)
            elif route_missing is not None:
                # A later heartbeat inside the grace window may have a fresh route. Do not freeze
                # a missing outcome early and do not invent a value from stale reserves.
                continue
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
                        route_source=state.reserve_source or state.venue,
                        route_event_id=state.last_event_id,
                        reserve_observed_at=state.last_reserve_at or state.last_event_at or now,
                        reserve_age_seconds=max(
                            0.0,
                            (
                                now - (state.last_reserve_at or state.last_event_at or now)
                            ).total_seconds(),
                        ),
                    )
                    primary_became_available = horizon == PRIMARY_HORIZON_SECONDS
                except ValueError:
                    observation.checkpoints[key] = LearningCheckpoint(
                        horizon_seconds=horizon,
                        observed_at=now,
                        missing_reason="executable_exit_quote_unavailable",
                    )
                self._observe_size_checkpoint(observation, state, horizon, now)
            primary_checkpoint_changed = (
                primary_checkpoint_changed or horizon == PRIMARY_HORIZON_SECONDS
            )
            changed += 1
        if len(observation.checkpoints) == len(LEARNING_HORIZONS_SECONDS):
            observation.status = LearningObservationStatus.COMPLETE
        if changed:
            self.database.save_learning_observation(observation)
            self._invalidate_timing_validation()
        if primary_checkpoint_changed:
            if primary_became_available:
                self._record_usable_outcome(observation)
            self._advance_entry_tournaments()
            self._retrain_if_ready(
                target_mode=observation.risk_mode,
                target_configuration=observation.configuration_fingerprint,
            )
            self._govern_skill_ensemble()
        if observation.status == LearningObservationStatus.COMPLETE:
            self._prune_complete_history()
        return changed

    def _observe_size_checkpoint(
        self,
        observation: LearningObservation,
        state: TokenState,
        horizon: int,
        now: datetime,
    ) -> None:
        key = str(horizon)
        network_fee = self.settings.network_fee_lamports + self.settings.priority_fee_lamports
        for trial in observation.size_trials.values():
            if key in trial.checkpoints:
                continue
            if (
                not trial.eligible_at_entry
                or trial.token_units is None
                or trial.entry_cost_lamports is None
            ):
                trial.checkpoints[key] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=now,
                    missing_reason=trial.entry_missing_reason or "size_trial_ineligible_at_entry",
                )
                continue
            try:
                exit_quote = quote_sell(
                    virtual_token_reserves=state.virtual_token_reserves,
                    virtual_sol_reserves=state.virtual_quote_reserves,
                    token_units=trial.token_units,
                    fee_bps=state.fee_bps or observation.fee_bps,
                    network_fee_lamports=network_fee,
                )
                net_return = (
                    exit_quote.wallet_sol_lamports - trial.entry_cost_lamports
                ) / trial.entry_cost_lamports
                trial.checkpoints[key] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=now,
                    net_return=max(-1.0, min(10.0, net_return)),
                    exit_value_lamports=exit_quote.wallet_sol_lamports,
                    route_source=state.reserve_source or state.venue,
                    route_event_id=state.last_event_id,
                    reserve_observed_at=state.last_reserve_at or state.last_event_at or now,
                    reserve_age_seconds=max(
                        0.0,
                        (
                            now - (state.last_reserve_at or state.last_event_at or now)
                        ).total_seconds(),
                    ),
                )
            except ValueError:
                trial.checkpoints[key] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=now,
                    missing_reason="size_trial_exit_quote_unavailable",
                )

    @staticmethod
    def _mark_size_trials_missing(
        observation: LearningObservation,
        horizon: int,
        now: datetime,
        reason: str,
    ) -> None:
        key = str(horizon)
        for trial in observation.size_trials.values():
            if key not in trial.checkpoints:
                trial.checkpoints[key] = LearningCheckpoint(
                    horizon_seconds=horizon,
                    observed_at=now,
                    missing_reason=reason,
                )

    def sample_due_checkpoints(
        self,
        states: dict[str, TokenState],
        now: datetime,
        *,
        live: bool,
        max_observations: int = MAX_CLOCK_CHECKPOINTS_PER_TICK,
    ) -> int:
        """Capture due outcomes from fresh cached routes without extra provider requests.

        Work is bounded per heartbeat and ordered by the oldest due observation. A token receiving
        no perfectly timed trade can therefore still produce an exact checkpoint, while stale or
        unverifiable reserves remain missing rather than becoming fabricated P/L.
        """

        if not live or max_observations < 1:
            return 0
        due = sorted(
            (
                observation
                for observation in self.observations.values()
                if observation.status == LearningObservationStatus.PENDING
                and any(
                    str(horizon) not in observation.checkpoints
                    and horizon
                    <= max(0.0, (now - observation.created_at).total_seconds())
                    <= horizon + CHECKPOINT_GRACE_SECONDS
                    for horizon in LEARNING_HORIZONS_SECONDS
                )
            ),
            key=lambda item: (
                _checkpoint_route_missing_reason(
                    states[item.mint],
                    now,
                    stale_after_seconds=self.settings.stale_market_seconds,
                    require_timestamp=True,
                )
                is not None
                if item.mint in states
                else True,
                item.created_at,
            ),
        )
        changed = 0
        for observation in due[:max_observations]:
            state = states.get(observation.mint)
            if state is None:
                continue
            changed += self.observe_market(state, now, live=True, cached=True)
        return changed

    def expire_checkpoints(
        self,
        now: datetime,
        *,
        states: dict[str, TokenState] | None = None,
    ) -> int:
        changed = 0
        primary_changed = False
        primary_cohorts: set[tuple[RiskMode, str | None]] = set()
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
                    missing_reason=(
                        "no_fresh_trade_near_horizon"
                        if states is None
                        else _expired_checkpoint_reason(
                            states.get(observation.mint),
                            now,
                            stale_after_seconds=self.settings.stale_market_seconds,
                        )
                    ),
                )
                self._mark_size_trials_missing(
                    observation,
                    horizon,
                    now,
                    observation.checkpoints[key].missing_reason or "checkpoint_window_elapsed",
                )
                item_changed = True
                changed += 1
                primary_changed = primary_changed or horizon == PRIMARY_HORIZON_SECONDS
                if horizon == PRIMARY_HORIZON_SECONDS:
                    primary_cohorts.add(
                        (observation.risk_mode, observation.configuration_fingerprint)
                    )
            if len(observation.checkpoints) == len(LEARNING_HORIZONS_SECONDS):
                observation.status = LearningObservationStatus.COMPLETE
            if item_changed:
                self.database.save_learning_observation(observation)
        if primary_changed:
            self._advance_entry_tournaments()
            for target_mode, target_configuration in sorted(
                primary_cohorts,
                key=lambda item: (item[0].value, item[1] or ""),
            ):
                self._retrain_if_ready(
                    target_mode=target_mode,
                    target_configuration=target_configuration,
                )
            self._govern_skill_ensemble()
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
        if live and self.mode == LearningMode.ACTIVE and self.active_skill_versions:
            return self._assess_active_skills(
                decision,
                baseline_actionable=baseline_actionable,
            )
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

    def _assess_active_skills(
        self,
        decision: Decision,
        *,
        baseline_actionable: bool,
    ) -> Decision:
        features = _feature_vector(decision)
        if features is None:
            return decision
        assessments: dict[str, dict[str, Any]] = {}
        applied_versions: list[str] = []
        reasons = list(decision.reasons)
        blockers = list(decision.blockers)
        action = decision.action
        planned_size = decision.planned_order_size_sol
        legacy_assessment: LearningAssessment | None = None
        for skill in (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
        ):
            version = self.active_skill_versions.get(skill.value)
            artifact = self.skill_artifacts.get(version or "")
            state = self._current_skill_state(skill)
            if (
                artifact is None
                or state is None
                or artifact.skill != skill
                or state.active_version != artifact.version
                or state.suspended_version == artifact.version
                or any(
                    self.active_skill_versions.get(dependency) != dependency_version
                    for dependency, dependency_version in state.active_dependencies.items()
                )
                or artifact.risk_mode != decision.risk_mode
                or artifact.configuration_fingerprint != decision.configuration_fingerprint
                or artifact.baseline_version != decision.model_version.split("+", maxsplit=1)[0]
                or not artifact.qualified
            ):
                continue
            prediction = _predict_skill_artifact(artifact, features)
            supported = _within_skill_artifact_support(artifact, features)
            rmse = float(artifact.metrics.get("validation_rmse") or 0.0)
            conservative = prediction - rmse if prediction is not None else None
            proposed = "baseline"
            applied = False
            if skill in {ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION}:
                proposed = (
                    "support"
                    if supported and conservative is not None and conservative > 0
                    else "veto"
                )
                applied = bool(action == DecisionAction.ENTER and baseline_actionable and supported)
                if skill == ChallengerSkill.ENTRY:
                    legacy_assessment = LearningAssessment(
                        model_version=artifact.version,
                        predicted_net_return=prediction or 0.0,
                        conservative_net_return=conservative or 0.0,
                        validation_rmse=rmse,
                        applied=applied,
                        verdict=(
                            "out_of_distribution"
                            if not supported
                            else "supports_entry"
                            if proposed == "support"
                            else "caution"
                        ),
                    )
                if applied and proposed == "veto":
                    action = DecisionAction.PASS
                    blockers.append(f"challenger_{skill.value}_veto")
                    reasons.append(f"The qualified Challenger {skill.value} skill preserved cash")
                elif applied:
                    reasons.append(f"The qualified Challenger {skill.value} skill agreed")
            else:
                selected = (
                    _nearest_size_multiplier(prediction)
                    if prediction is not None and supported
                    else 1.0
                )
                if selected > 1.0 and (
                    decision.integrity_assessment is None
                    or decision.integrity_assessment.state != MarketIntegrityState.CLEAN
                ):
                    selected = 1.0
                    proposed = "baseline_integrity_guard"
                elif (
                    selected > 1.0
                    and planned_size is not None
                    and decision.sizing_assessment is not None
                    and decision.sizing_assessment.maximum_size_sol is not None
                    and planned_size * selected > decision.sizing_assessment.maximum_size_sol + 1e-9
                ):
                    selected = 1.0
                    proposed = "baseline_capacity_guard"
                else:
                    proposed = _size_trial_key(selected)
                applied = bool(
                    action == DecisionAction.ENTER
                    and baseline_actionable
                    and supported
                    and planned_size is not None
                    and selected != 1.0
                )
                if applied and planned_size is not None:
                    planned_size = planned_size * selected
                    reasons.append(f"The qualified Challenger sizing skill selected {selected:g}x")
            receipt = ChallengerEvaluationReceipt(
                artifact_version=artifact.version,
                skill=skill,
                evaluated_at=decision.created_at,
                prediction=prediction,
                conservative_value=conservative,
                in_distribution=supported,
                proposed_action=proposed,
                baseline_actionable=baseline_actionable,
                parameters={
                    "applied": applied,
                    **(
                        {
                            "selected_multiplier": selected,
                            "baseline_size_sol": (
                                decision.planned_order_size_sol
                                if decision.planned_order_size_sol is not None
                                else 0.0
                            ),
                        }
                        if skill == ChallengerSkill.SIZING
                        else {}
                    ),
                },
            )
            assessments[skill.value] = receipt.model_dump(mode="json")
            if applied:
                applied_versions.append(artifact.version)
        model_version = decision.model_version
        if applied_versions:
            model_version = "+".join((model_version, *applied_versions))
        return decision.model_copy(
            update={
                "action": action,
                "reasons": reasons,
                "blockers": blockers,
                "planned_order_size_sol": planned_size,
                "model_version": model_version,
                "learning_assessment": legacy_assessment,
                "challenger_assessments": assessments,
            }
        )

    def status(self, *, demo_mode: bool) -> dict[str, Any]:
        samples = self._training_rows(
            mode=self.current_risk_mode,
            configuration_fingerprint=self.configuration_fingerprint(),
            match_configuration=True,
        )
        timing_validation = {mode.value: self.hold_timing_validation(mode) for mode in RISK_LIMITS}
        activation_candidate = self._activation_candidate()
        skill_activation_candidate = self._skill_activation_candidate()
        entry_active_version = self.active_skill_versions.get(ChallengerSkill.ENTRY.value)
        active_health = (
            self._skill_health(ChallengerSkill.ENTRY, entry_active_version)
            if entry_active_version is not None
            else self.active_model_health()
        )
        active_health = {
            "supported_count": 0,
            "vetoed_count": 0,
            "winner_vetoed_count": 0,
            "baseline_mean_return": None,
            "learner_mean_return": None,
            **active_health,
        }
        entry_availability = self.entry_outcome_availability()
        pending = sum(
            item.status == LearningObservationStatus.PENDING for item in self.observations.values()
        )
        missing = sum(
            (checkpoint := item.checkpoints.get(str(PRIMARY_HORIZON_SECONDS))) is not None
            and checkpoint.net_return is None
            for item in self.observations.values()
        )
        unavailable_reasons: dict[str, int] = {}
        for item in self.observations.values():
            checkpoint = item.checkpoints.get(str(PRIMARY_HORIZON_SECONDS))
            if checkpoint is None or checkpoint.net_return is not None:
                continue
            reason = checkpoint.missing_reason or "unspecified"
            unavailable_reasons[reason] = unavailable_reasons.get(reason, 0) + 1
        latest = self.latest_model
        if self.mode == LearningMode.OFF:
            state = "paused"
        elif self.mode == LearningMode.ACTIVE:
            state = "active"
        elif latest is None:
            state = "collecting"
        elif activation_candidate is not None or skill_activation_candidate is not None:
            state = "ready"
        else:
            state = "challenger_testing"
        next_training = (
            max(0, MINIMUM_TRAINING_SAMPLES - len(samples))
            if latest is None
            else max(0, RETRAIN_SAMPLE_INTERVAL - self._new_outcomes_since_model(latest))
        )
        qualification_gates = _entry_qualification_gates(
            latest,
            usable_outcomes=len(samples),
            current_availability=entry_availability,
            activation_available=(
                activation_candidate is not None or skill_activation_candidate is not None
            ),
        )
        skill_statuses = self.skill_statuses()
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
            "unavailable_outcome_reasons": unavailable_reasons,
            "clock_checkpoint_limit": MAX_CLOCK_CHECKPOINTS_PER_TICK,
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
                self.mode == LearningMode.ACTIVE
                and (
                    ChallengerSkill.EXIT.value in self.active_skill_versions
                    or (
                        self.active_model is not None and timing_validation[mode.value]["qualified"]
                    )
                )
                for mode in RISK_LIMITS
            ),
            "latest_model": _model_summary(latest),
            "active_model": _model_summary(self.active_model),
            "active_model_health": active_health,
            "activation_available": (
                activation_candidate is not None or skill_activation_candidate is not None
            ),
            "consent_granted": self.consent_granted,
            "active_skill_versions": dict(self.active_skill_versions),
            "skills": skill_statuses,
            "champion_journey": self.champion_journey(),
            "challenger_common_forward_minimum": TOURNAMENT_MINIMUM_COMMON_OUTCOMES,
            "challenger_minimum_availability": TOURNAMENT_MINIMUM_AVAILABILITY,
            "qualification_gates": qualification_gates,
            "qualification_passed": sum(gate["state"] == "passed" for gate in qualification_gates),
            "qualification_total": len(qualification_gates),
            "lessons": _lessons(latest),
            "guardrails": [
                "Never trains on synthetic Demo Market data",
                "Never overrides structural safety, confidence, danger, impact, or drawdown gates",
                "Can veto a baseline entry but cannot invent a new entry",
                "Entry, manipulation, sizing, and exit qualify and suspend independently",
                "One consent lets later skills join only after fresh combined forward proof",
                "Sizing stays inside Baseline impact, exposure, cash, and integrity limits",
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

    def skill_statuses(self) -> list[dict[str, Any]]:
        statuses: list[dict[str, Any]] = []
        for skill in (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        ):
            state = self._current_skill_state(skill)
            latest = (
                self.skill_artifacts.get(state.latest_candidate_version or "")
                if state is not None
                else None
            )
            champion = (
                self.skill_artifacts.get(state.champion_version or "")
                if state is not None
                else None
            )
            active_version = self.active_skill_versions.get(skill.value)
            if (
                state is not None
                and state.suspended_version is not None
                and state.suspended_version == state.champion_version
            ):
                status = "suspended"
            elif active_version:
                status = "active"
            elif state is not None and state.testing_version:
                status = "candidate_testing"
            elif champion is not None:
                status = "qualified"
            elif latest is not None:
                status = "collecting_proof"
            else:
                status = "collecting"
            health = (
                self._skill_health(skill, active_version)
                if active_version is not None
                else {
                    "state": "suspended" if status == "suspended" else "inactive",
                    "model_version": active_version,
                    "observed_count": 0,
                    "usable_count": 0,
                    "minimum_samples": ACTIVE_HEALTH_MINIMUM_SAMPLES,
                    "availability_fraction": 0.0,
                    "estimated_uplift": None,
                    "uplift_upper_bound": None,
                }
            )
            statuses.append(
                {
                    "skill": skill.value,
                    "label": {
                        ChallengerSkill.ENTRY: "Entry selection",
                        ChallengerSkill.MANIPULATION: "Manipulation defence",
                        ChallengerSkill.SIZING: "Position sizing",
                        ChallengerSkill.EXIT: "Exit timing",
                    }[skill],
                    "state": status,
                    "latest_candidate": _skill_artifact_summary(latest),
                    "testing_version": state.testing_version if state is not None else None,
                    "champion": _skill_artifact_summary(champion),
                    "active_version": active_version,
                    "common_forward_count": (
                        state.common_forward_count if state is not None else 0
                    ),
                    "tournament": dict(state.last_tournament) if state is not None else {},
                    "health": health,
                    "gates": _skill_qualification_gates(skill, latest),
                }
            )
        return statuses

    def champion_journey(self) -> list[dict[str, Any]]:
        """Return recent Champion milestones for only the exact active cohort."""

        events = [
            event
            for skill in (
                ChallengerSkill.ENTRY,
                ChallengerSkill.MANIPULATION,
                ChallengerSkill.SIZING,
                ChallengerSkill.EXIT,
            )
            if (state := self._current_skill_state(skill)) is not None
            for event in state.champion_journey
        ]
        return [
            event.model_dump(mode="json")
            for event in sorted(events, key=lambda item: item.occurred_at, reverse=True)[
                :MAX_CHAMPION_JOURNEY_EVENTS
            ]
        ]

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
        exit_version = self.active_skill_versions.get(ChallengerSkill.EXIT.value)
        exit_artifact = self.skill_artifacts.get(exit_version or "")
        if (
            self.mode == LearningMode.ACTIVE
            and exit_artifact is not None
            and exit_artifact.qualified
            and exit_artifact.skill == ChallengerSkill.EXIT
            and exit_artifact.risk_mode == mode
            and exit_artifact.configuration_fingerprint == self.configuration_fingerprint()
        ):
            selected = int(exit_artifact.parameters.get("selected_horizon_seconds", 0))
            if 0 < selected <= limits.max_hold_seconds:
                return selected
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

    def _freeze_skill_evaluations(self, observation: LearningObservation) -> None:
        """Freeze candidate/champion predictions before the later outcome can exist."""

        cohort_key = _challenger_cohort_key(
            observation.risk_mode,
            observation.configuration_fingerprint,
            observation.baseline_version,
            observation.feature_schema_version,
        )
        if cohort_key is None:
            return
        for skill in (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        ):
            state = self.skill_states.get((cohort_key, skill))
            if state is None:
                continue
            versions = {
                version
                for version in (
                    state.latest_candidate_version,
                    state.testing_version,
                    state.champion_version,
                )
                if version is not None
            }
            for version in versions:
                artifact = self.skill_artifacts.get(version)
                if artifact is None or artifact.skill != skill:
                    continue
                if (
                    artifact.schema_version == "challenger-skill-coach-v1"
                    and observation.active_skill_versions != artifact.dependency_versions
                ):
                    # Coach policies are proved against one exact active ensemble. If that
                    # ensemble changes, new observations must not silently become evidence for
                    # the old policy. Native artifacts retain their existing composition path.
                    continue
                if skill == ChallengerSkill.EXIT:
                    selected_horizon = int(
                        artifact.parameters.get(
                            "selected_horizon_seconds",
                            RISK_LIMITS[observation.risk_mode].max_hold_seconds,
                        )
                    )
                    observation.challenger_evaluations[version] = ChallengerEvaluationReceipt(
                        artifact_version=version,
                        skill=skill,
                        evaluated_at=observation.created_at,
                        in_distribution=True,
                        proposed_action=str(selected_horizon),
                        baseline_actionable=observation.baseline_actionable,
                    )
                    continue
                prediction = _predict_skill_artifact(artifact, observation.features)
                in_distribution = _within_skill_artifact_support(artifact, observation.features)
                validation_rmse = float(artifact.metrics.get("validation_rmse") or 0.0)
                conservative = (
                    prediction - validation_rmse
                    if prediction is not None and skill != ChallengerSkill.SIZING
                    else prediction
                )
                proposed_action = (
                    _size_trial_key(_nearest_size_multiplier(prediction))
                    if skill == ChallengerSkill.SIZING
                    and prediction is not None
                    and in_distribution
                    else "1"
                    if skill == ChallengerSkill.SIZING
                    else "support"
                    if in_distribution and conservative is not None and conservative > 0
                    else "veto"
                )
                observation.challenger_evaluations[version] = ChallengerEvaluationReceipt(
                    artifact_version=version,
                    skill=skill,
                    evaluated_at=observation.created_at,
                    prediction=prediction,
                    conservative_value=conservative,
                    in_distribution=in_distribution,
                    proposed_action=proposed_action,
                    baseline_actionable=observation.baseline_actionable,
                )

    def _publish_entry_artifact(
        self,
        model: LearningModel,
        *,
        baseline_version: str,
        evidence_started_at: datetime | None,
        evidence_ended_at: datetime | None,
    ) -> None:
        configuration = model.configuration_fingerprint
        if (
            model.risk_mode is None
            or not configuration
            or baseline_version not in LEARNABLE_BASELINE_VERSIONS
        ):
            # Legacy/ambiguous cohorts remain fully available through LearningModel, but are not
            # silently relabelled as v1 multi-skill evidence.
            return
        cohort_key = _challenger_cohort_key(
            model.risk_mode,
            configuration,
            baseline_version,
            FEATURE_SCHEMA_VERSION,
        )
        if cohort_key is None:
            return
        artifact = ChallengerSkillArtifact(
            version=f"{SKILL_ARTIFACT_VERSION_PREFIX}entry-{model.version}",
            skill=ChallengerSkill.ENTRY,
            created_at=model.created_at,
            risk_mode=model.risk_mode,
            configuration_fingerprint=configuration,
            baseline_version=baseline_version,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            evidence_started_at=evidence_started_at,
            evidence_ended_at=evidence_ended_at,
            outcomes_seen=model.outcomes_seen,
            sample_count=model.sample_count,
            training_count=model.training_count,
            validation_count=model.validation_count,
            embargoed_count=model.embargoed_count,
            feature_names=list(model.feature_names),
            parameters={
                "means": list(model.means),
                "scales": list(model.scales),
                "coefficients": list(model.coefficients),
            },
            metrics={
                "validation_rmse": model.validation_rmse,
                "naive_rmse": model.naive_rmse,
                "rank_fit": model.learner_correlation,
                "baseline_rank_fit": model.baseline_correlation,
                "top_return": model.learner_top_mean_return,
                "top_uplift": (model.learner_top_mean_return - model.baseline_top_mean_return),
                "outcome_availability": model.outcome_availability_fraction,
                "policy_samples": model.policy_validation_count,
                "policy_vetoes": model.policy_veto_count,
                "policy_winner_vetoes": model.policy_winner_veto_count,
                "policy_uplift_lower": model.policy_uplift_lower_bound,
            },
            qualified=model.qualified,
            qualification_reasons=([] if model.qualified else ["entry_proof_gates_not_met"]),
        )
        self._register_skill_artifact(artifact, cohort_key)

    def _publish_manipulation_artifact(
        self,
        *,
        risk_mode: RiskMode,
        configuration_fingerprint: str | None,
        baseline_version: str,
        rows: list[tuple[LearningObservation, float]],
        training: list[tuple[LearningObservation, float]],
        validation: list[tuple[LearningObservation, float]],
        resolved_count: int,
        embargoed_count: int,
    ) -> None:
        if (
            not configuration_fingerprint
            or baseline_version not in LEARNABLE_BASELINE_VERSIONS
            or not training
            or not validation
        ):
            return
        cohort_key = _challenger_cohort_key(
            risk_mode,
            configuration_fingerprint,
            baseline_version,
            FEATURE_SCHEMA_VERSION,
        )
        fitted = _fit(training, feature_names=MANIPULATION_FEATURE_NAMES)
        if cohort_key is None or fitted is None:
            return
        predictions = [
            _predict_named_parts(fitted, item.features, MANIPULATION_FEATURE_NAMES)
            for item, _ in validation
        ]
        outcomes = [outcome for _, outcome in validation]
        rmse = _rmse(predictions, outcomes)
        naive_mean = fmean(outcome for _, outcome in training)
        naive_rmse = _rmse([naive_mean] * len(outcomes), outcomes)
        in_distribution = [
            _within_named_parts_support(fitted, item.features, MANIPULATION_FEATURE_NAMES)
            for item, _ in validation
        ]
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
            supported and prediction - rmse > 0 for _, _, prediction, supported in policy_rows
        ]
        policy_deltas = [
            0.0 if support else -outcome
            for (_, outcome, _, _), support in zip(policy_rows, policy_support, strict=True)
        ]
        policy_vetoes = len(policy_support) - sum(policy_support)
        winner_vetoes = sum(
            not support and outcome > 0
            for (_, outcome, _, _), support in zip(policy_rows, policy_support, strict=True)
        )
        uplift_lower = _mean_lower_bound(policy_deltas, z_score=ENTRY_POLICY_Z_SCORE)
        in_distribution_fraction = sum(in_distribution) / len(in_distribution)
        outcome_availability = len(rows) / resolved_count if resolved_count else 0.0
        winner_veto_fraction = winner_vetoes / policy_vetoes if policy_vetoes else 0.0
        qualified = bool(
            outcome_availability >= ENTRY_MINIMUM_OUTCOME_AVAILABILITY
            and in_distribution_fraction >= MANIPULATION_MINIMUM_IN_DISTRIBUTION_FRACTION
            and len(policy_rows) >= ENTRY_MINIMUM_POLICY_SAMPLES
            and policy_vetoes >= ENTRY_MINIMUM_POLICY_VETOES
            and uplift_lower is not None
            and uplift_lower > 0
            and winner_veto_fraction <= MANIPULATION_MAXIMUM_WINNER_VETO_FRACTION
        )
        means, scales, coefficients = fitted
        artifact = ChallengerSkillArtifact(
            version=(
                f"{SKILL_ARTIFACT_VERSION_PREFIX}manipulation-{risk_mode.value}-"
                f"{configuration_fingerprint}-{self.outcomes_seen}-"
                f"{int(datetime.now(UTC).timestamp())}"
            ),
            skill=ChallengerSkill.MANIPULATION,
            risk_mode=risk_mode,
            configuration_fingerprint=configuration_fingerprint,
            baseline_version=baseline_version,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            evidence_started_at=rows[0][0].created_at,
            evidence_ended_at=rows[-1][0].created_at,
            outcomes_seen=self.outcomes_seen,
            sample_count=len(rows),
            training_count=len(training),
            validation_count=len(validation),
            embargoed_count=embargoed_count,
            feature_names=list(MANIPULATION_FEATURE_NAMES),
            parameters={
                "means": means,
                "scales": scales,
                "coefficients": coefficients,
            },
            metrics={
                "validation_rmse": rmse,
                "naive_rmse": naive_rmse,
                "outcome_availability": outcome_availability,
                "in_distribution_fraction": in_distribution_fraction,
                "policy_samples": len(policy_rows),
                "policy_vetoes": policy_vetoes,
                "policy_winner_vetoes": winner_vetoes,
                "policy_winner_veto_fraction": winner_veto_fraction,
                "policy_mean_uplift": fmean(policy_deltas) if policy_deltas else None,
                "policy_uplift_lower": uplift_lower,
            },
            qualified=qualified,
            qualification_reasons=([] if qualified else ["manipulation_proof_gates_not_met"]),
        )
        self._register_skill_artifact(artifact, cohort_key)

    def _publish_sizing_artifact(
        self,
        *,
        risk_mode: RiskMode,
        configuration_fingerprint: str | None,
        baseline_version: str,
        rows: list[tuple[LearningObservation, float]],
        training: list[tuple[LearningObservation, float]],
        validation: list[tuple[LearningObservation, float]],
        embargoed_count: int,
    ) -> None:
        if not configuration_fingerprint or baseline_version not in LEARNABLE_BASELINE_VERSIONS:
            return
        cohort_key = _challenger_cohort_key(
            risk_mode,
            configuration_fingerprint,
            baseline_version,
            FEATURE_SCHEMA_VERSION,
        )
        training_targets = [
            (observation, target)
            for observation, _ in training
            if (target := _best_size_multiplier(observation)) is not None
        ]
        fitted = _fit(training_targets, feature_names=SIZING_FEATURE_NAMES)
        if cohort_key is None or fitted is None:
            return
        actionable_validation = [
            observation
            for observation, _ in validation
            if observation.baseline_action == DecisionAction.ENTER
            and observation.baseline_actionable
        ]
        policy_rows: list[tuple[LearningObservation, float, float, bool]] = []
        in_distribution_count = 0
        for observation in actionable_validation:
            supported = _within_named_parts_support(
                fitted, observation.features, SIZING_FEATURE_NAMES
            )
            in_distribution_count += int(supported)
            predicted = _predict_named_parts(fitted, observation.features, SIZING_FEATURE_NAMES)
            selected = _nearest_size_multiplier(predicted) if supported else 1.0
            selected_value = _size_trial_value(observation, selected)
            baseline_value = _size_trial_value(observation, 1.0)
            if selected_value is None or baseline_value is None:
                continue
            policy_rows.append((observation, selected_value, baseline_value, supported))
        policy_deltas = [selected - baseline for _, selected, baseline, _ in policy_rows]
        changes = sum(
            _nearest_size_multiplier(
                _predict_named_parts(fitted, observation.features, SIZING_FEATURE_NAMES)
            )
            != 1.0
            for observation, _, _, supported in policy_rows
            if supported
        )
        harm_count = sum(delta < 0 for delta in policy_deltas)
        harm_fraction = harm_count / len(policy_deltas) if policy_deltas else 0.0
        availability = (
            len(policy_rows) / len(actionable_validation) if actionable_validation else 0.0
        )
        in_distribution_fraction = (
            in_distribution_count / len(actionable_validation) if actionable_validation else 0.0
        )
        uplift_lower = _mean_lower_bound(policy_deltas, z_score=ENTRY_POLICY_Z_SCORE)
        qualified = bool(
            len(policy_rows) >= ENTRY_MINIMUM_POLICY_SAMPLES
            and availability >= ENTRY_MINIMUM_OUTCOME_AVAILABILITY
            and in_distribution_fraction >= MANIPULATION_MINIMUM_IN_DISTRIBUTION_FRACTION
            and changes >= SIZING_MINIMUM_POLICY_CHANGES
            and uplift_lower is not None
            and uplift_lower > 0
            and harm_fraction <= SIZING_MAXIMUM_HARM_FRACTION
        )
        means, scales, coefficients = fitted
        artifact = ChallengerSkillArtifact(
            version=(
                f"{SKILL_ARTIFACT_VERSION_PREFIX}sizing-{risk_mode.value}-"
                f"{configuration_fingerprint}-{self.outcomes_seen}-"
                f"{int(datetime.now(UTC).timestamp())}"
            ),
            skill=ChallengerSkill.SIZING,
            risk_mode=risk_mode,
            configuration_fingerprint=configuration_fingerprint,
            baseline_version=baseline_version,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            evidence_started_at=rows[0][0].created_at,
            evidence_ended_at=rows[-1][0].created_at,
            outcomes_seen=self.outcomes_seen,
            sample_count=len(rows),
            training_count=len(training_targets),
            validation_count=len(actionable_validation),
            embargoed_count=embargoed_count,
            feature_names=list(SIZING_FEATURE_NAMES),
            parameters={
                "means": means,
                "scales": scales,
                "coefficients": coefficients,
                "multipliers": list(SIZING_MULTIPLIERS),
            },
            metrics={
                "policy_samples": len(policy_rows),
                "policy_changes": changes,
                "outcome_availability": availability,
                "in_distribution_fraction": in_distribution_fraction,
                "mean_uplift": fmean(policy_deltas) if policy_deltas else None,
                "uplift_lower_bound": uplift_lower,
                "harm_count": harm_count,
                "harm_fraction": harm_fraction,
            },
            qualified=qualified,
            qualification_reasons=[] if qualified else ["sizing_proof_gates_not_met"],
        )
        self._register_skill_artifact(artifact, cohort_key)

    def _publish_exit_artifact(
        self,
        *,
        risk_mode: RiskMode,
        configuration_fingerprint: str | None,
        baseline_version: str,
    ) -> None:
        if not configuration_fingerprint or baseline_version not in LEARNABLE_BASELINE_VERSIONS:
            return
        cohort_key = _challenger_cohort_key(
            risk_mode,
            configuration_fingerprint,
            baseline_version,
            FEATURE_SCHEMA_VERSION,
        )
        if cohort_key is None:
            return
        baseline_horizon = RISK_LIMITS[risk_mode].max_hold_seconds
        candidates = tuple(
            horizon for horizon in LEARNING_HORIZONS_SECONDS if horizon <= baseline_horizon
        )
        evidence = [
            observation
            for observation in sorted(self.observations.values(), key=lambda item: item.created_at)
            if observation.risk_mode == risk_mode
            and observation.configuration_fingerprint == configuration_fingerprint
            and observation.baseline_version == baseline_version
            and observation.feature_schema_version == FEATURE_SCHEMA_VERSION
            and observation.baseline_action == DecisionAction.ENTER
            and observation.baseline_actionable
            and all(str(horizon) in observation.checkpoints for horizon in candidates)
        ][-HOLD_TIMING_WINDOW_OBSERVATIONS:]
        if len(evidence) < HOLD_TIMING_MINIMUM_SAMPLES:
            return
        validation_count = max(MINIMUM_VALIDATION_SAMPLES, len(evidence) // 3)
        raw_training = evidence[:-validation_count]
        validation = evidence[-validation_count:]
        validation_start = validation[0].created_at
        training = [
            observation
            for observation in raw_training
            if all(
                observation.checkpoints[str(horizon)].observed_at <= validation_start
                for horizon in candidates
            )
        ]
        if len(training) < MINIMUM_FIT_SAMPLES:
            return
        training_utilities = {
            horizon: _mean_horizon_utility(training, horizon) for horizon in candidates
        }
        selected = max(
            candidates,
            key=lambda horizon: (
                training_utilities[horizon],
                horizon == baseline_horizon,
            ),
        )
        validation_deltas = [
            _checkpoint_utility(observation, selected)
            - _checkpoint_utility(observation, baseline_horizon)
            for observation in validation
        ]
        uplift_lower = _mean_lower_bound(validation_deltas, z_score=HOLD_TIMING_Z_SCORE)
        availability = sum(
            observation.checkpoints[str(selected)].net_return is not None
            and observation.checkpoints[str(baseline_horizon)].net_return is not None
            for observation in validation
        ) / len(validation)
        qualified = bool(
            selected < baseline_horizon
            and training_utilities[selected]
            >= training_utilities[baseline_horizon] + HOLD_TIMING_MINIMUM_UPLIFT
            and uplift_lower is not None
            and uplift_lower >= HOLD_TIMING_MINIMUM_UPLIFT
            and availability >= HOLD_TIMING_MINIMUM_AVAILABILITY
        )
        artifact = ChallengerSkillArtifact(
            version=(
                f"{SKILL_ARTIFACT_VERSION_PREFIX}exit-{risk_mode.value}-"
                f"{configuration_fingerprint}-{self.outcomes_seen}-"
                f"{int(datetime.now(UTC).timestamp())}"
            ),
            skill=ChallengerSkill.EXIT,
            risk_mode=risk_mode,
            configuration_fingerprint=configuration_fingerprint,
            baseline_version=baseline_version,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            evidence_started_at=evidence[0].created_at,
            evidence_ended_at=evidence[-1].created_at,
            outcomes_seen=self.outcomes_seen,
            sample_count=len(evidence),
            training_count=len(training),
            validation_count=len(validation),
            embargoed_count=len(raw_training) - len(training),
            parameters={
                "selected_horizon_seconds": selected,
                "baseline_horizon_seconds": baseline_horizon,
                "hard_max_hold_seconds": RISK_LIMITS[risk_mode].hard_max_hold_seconds,
            },
            metrics={
                "selected_training_utility": training_utilities[selected],
                "baseline_training_utility": training_utilities[baseline_horizon],
                "selected_validation_utility": _mean_horizon_utility(validation, selected),
                "baseline_validation_utility": _mean_horizon_utility(validation, baseline_horizon),
                "validation_uplift_lower_bound": uplift_lower,
                "validation_availability_fraction": availability,
            },
            qualified=qualified,
            qualification_reasons=[] if qualified else ["exit_proof_gates_not_met"],
        )
        self._register_skill_artifact(artifact, cohort_key)

    def _register_skill_artifact(
        self,
        artifact: ChallengerSkillArtifact,
        cohort_key: str,
    ) -> None:
        self.database.save_challenger_artifact(artifact)
        self.skill_artifacts[artifact.version] = artifact
        key = (cohort_key, artifact.skill)
        state = self.skill_states.get(key) or ChallengerSkillState(
            cohort_key=cohort_key,
            skill=artifact.skill,
            risk_mode=artifact.risk_mode,
            configuration_fingerprint=artifact.configuration_fingerprint,
            baseline_version=artifact.baseline_version,
            feature_schema_version=artifact.feature_schema_version,
        )
        state.latest_candidate_version = artifact.version
        if artifact.qualified:
            if state.champion_version is None:
                state.champion_version = artifact.version
                state.last_tournament = {
                    "result": "first_champion",
                    "candidate_version": artifact.version,
                    "common_usable_count": 0,
                }
                self._append_champion_event(
                    state,
                    kind="first_champion",
                    candidate_version=artifact.version,
                    previous_champion_version=None,
                    champion_version=artifact.version,
                    occurred_at=artifact.created_at,
                )
            elif (
                state.testing_version is None
                and artifact.version != state.champion_version
                and artifact.version not in state.rejected_versions
            ):
                state.testing_version = artifact.version
                state.common_forward_count = 0
                state.last_tournament = {
                    "result": "collecting",
                    "candidate_version": artifact.version,
                    "champion_version": state.champion_version,
                    "common_usable_count": 0,
                }
        state.updated_at = datetime.now(UTC)
        self.skill_states[key] = state
        self.database.save_challenger_skill_state(state)

    def seed_coach_candidate(
        self,
        hypothesis: CoachHypothesis,
    ) -> tuple[str | None, str]:
        """Hand one supported Coach policy to the normal Challenger tournament path."""

        if (
            hypothesis.state != CoachExperimentState.PROMISING
            or hypothesis.contribution_state not in {"ready", "waiting_for_champion"}
            or hypothesis.baseline_version not in LEARNABLE_BASELINE_VERSIONS
            or hypothesis.feature_schema_version != FEATURE_SCHEMA_VERSION
            or hypothesis.risk_mode != self.current_risk_mode
            or hypothesis.configuration_fingerprint != self.configuration_fingerprint()
            or hypothesis.dependency_versions != self.active_skill_versions
            or not _coach_policy_is_allowlisted(hypothesis)
        ):
            return None, "coach_context_stale"
        cohort_key = _challenger_cohort_key(
            hypothesis.risk_mode,
            hypothesis.configuration_fingerprint,
            hypothesis.baseline_version,
            hypothesis.feature_schema_version,
        )
        if cohort_key is None:
            return None, "coach_context_unavailable"
        state = self.skill_states.get((cohort_key, hypothesis.skill))
        if state is None or state.champion_version is None:
            return None, "waiting_for_champion"
        version = (
            f"{SKILL_ARTIFACT_VERSION_PREFIX}coach-{hypothesis.skill.value}-"
            f"{hashlib.sha256(hypothesis.hypothesis_id.encode()).hexdigest()[:20]}"
        )
        if version in self.skill_artifacts:
            return version, "handed_off"
        parameters: dict[str, Any] = {
            "coach_policy": {
                "hypothesis_id": hypothesis.hypothesis_id,
                "kind": hypothesis.kind.value,
                "conditions": [
                    condition.model_dump(mode="json") for condition in hypothesis.conditions
                ],
                "size_multiplier": hypothesis.size_multiplier,
                "hold_seconds": hypothesis.hold_seconds,
            },
        }
        if hypothesis.hold_seconds is not None:
            parameters.update(
                {
                    "selected_horizon_seconds": hypothesis.hold_seconds,
                    "baseline_horizon_seconds": (
                        hypothesis.baseline_hold_seconds
                        or RISK_LIMITS[hypothesis.risk_mode].max_hold_seconds
                    ),
                    "hard_max_hold_seconds": RISK_LIMITS[
                        hypothesis.risk_mode
                    ].hard_max_hold_seconds,
                }
            )
        artifact = ChallengerSkillArtifact(
            version=version,
            schema_version="challenger-skill-coach-v1",
            skill=hypothesis.skill,
            created_at=datetime.now(UTC),
            risk_mode=hypothesis.risk_mode,
            configuration_fingerprint=hypothesis.configuration_fingerprint,
            baseline_version=hypothesis.baseline_version,
            feature_schema_version=hypothesis.feature_schema_version,
            evidence_started_at=hypothesis.cutoff_at,
            evidence_ended_at=hypothesis.resolved_at,
            outcomes_seen=self.outcomes_seen,
            sample_count=hypothesis.forward_usable_count,
            training_count=hypothesis.discovery_usable_count,
            validation_count=hypothesis.forward_usable_count,
            feature_names=[condition.feature_name for condition in hypothesis.conditions],
            parameters=parameters,
            metrics={
                "validation_rmse": 0.0,
                "forward_availability_fraction": hypothesis.forward_availability_fraction,
                "forward_season_count": hypothesis.forward_season_count,
                "forward_mean_uplift": hypothesis.forward_mean_uplift,
                "forward_uplift_lower_bound": hypothesis.forward_uplift_lower_bound,
                "coach_seeded": True,
            },
            dependency_versions=dict(hypothesis.dependency_versions),
            qualified=True,
        )
        self._register_skill_artifact(artifact, cohort_key)
        return version, "handed_off"

    def _append_champion_event(
        self,
        state: ChallengerSkillState,
        *,
        kind: Literal["first_champion", "promoted", "defended", "inconclusive"],
        candidate_version: str,
        previous_champion_version: str | None,
        champion_version: str,
        common_observed_count: int = 0,
        common_usable_count: int = 0,
        availability_fraction: float = 0.0,
        mean_uplift: float | None = None,
        uplift_lower_bound: float | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Append one bounded, restart-safe milestone without inventing old history."""

        identity = "\n".join(
            (
                state.cohort_key,
                state.skill.value,
                kind,
                candidate_version,
                previous_champion_version or "",
                champion_version,
            )
        )
        event_id = f"champion-event-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
        if any(event.event_id == event_id for event in state.champion_journey):
            return
        state.champion_journey = [
            *state.champion_journey,
            ChallengerChampionEvent(
                event_id=event_id,
                occurred_at=occurred_at or datetime.now(UTC),
                skill=state.skill,
                kind=kind,
                candidate_version=candidate_version,
                previous_champion_version=previous_champion_version,
                champion_version=champion_version,
                common_observed_count=common_observed_count,
                common_usable_count=common_usable_count,
                availability_fraction=availability_fraction,
                mean_uplift=mean_uplift,
                uplift_lower_bound=uplift_lower_bound,
            ),
        ][-MAX_CHAMPION_JOURNEY_EVENTS:]

    def _advance_entry_tournaments(self) -> None:
        """Compare contender and champion only on predictions both froze in advance."""

        primary_key = str(PRIMARY_HORIZON_SECONDS)
        current_cohort_key = _challenger_cohort_key(
            self.current_risk_mode,
            self.configuration_fingerprint(),
            self.baseline_version(),
            FEATURE_SCHEMA_VERSION,
        )
        for key, state in list(self.skill_states.items()):
            if (
                key[0] != current_cohort_key
                or state.skill
                not in {
                    ChallengerSkill.ENTRY,
                    ChallengerSkill.MANIPULATION,
                    ChallengerSkill.SIZING,
                    ChallengerSkill.EXIT,
                }
                or not state.testing_version
            ):
                continue
            candidate_version = state.testing_version
            champion_version = state.champion_version
            candidate = self.skill_artifacts.get(candidate_version)
            champion = self.skill_artifacts.get(champion_version or "")
            if candidate is None or champion is None:
                state.suspended_version = candidate_version
                state.suspension_reason = "tournament_artifact_unavailable"
                state.suspended_at = datetime.now(UTC)
                state.testing_version = None
                state.updated_at = datetime.now(UTC)
                self.database.save_challenger_skill_state(state)
                continue
            if (
                candidate.schema_version == "challenger-skill-coach-v1"
                and candidate.dependency_versions != self.active_skill_versions
            ):
                if candidate_version not in state.rejected_versions:
                    state.rejected_versions.append(candidate_version)
                    state.rejected_versions = state.rejected_versions[-MAX_MODEL_VERSIONS:]
                state.testing_version = None
                state.last_tournament = {
                    "result": "context_stale",
                    "candidate_version": candidate_version,
                    "champion_version": champion.version,
                    "common_observed_count": 0,
                    "common_usable_count": 0,
                }
                state.updated_at = datetime.now(UTC)
                self.database.save_challenger_skill_state(state)
                continue
            resolved: list[LearningObservation] = []
            for observation in sorted(self.observations.values(), key=lambda item: item.created_at):
                if (
                    observation.risk_mode != state.risk_mode
                    or observation.configuration_fingerprint != state.configuration_fingerprint
                    or observation.baseline_version != state.baseline_version
                    or observation.feature_schema_version != state.feature_schema_version
                    or observation.baseline_action != DecisionAction.ENTER
                    or not observation.baseline_actionable
                    or candidate_version not in observation.challenger_evaluations
                    or champion.version not in observation.challenger_evaluations
                ):
                    continue
                if not (
                    _skill_receipt_outcome_resolved(
                        observation,
                        observation.challenger_evaluations[candidate_version],
                    )
                    and _skill_receipt_outcome_resolved(
                        observation,
                        observation.challenger_evaluations[champion.version],
                    )
                ):
                    continue
                resolved.append(observation)
            usable = []
            for observation in resolved:
                candidate_receipt = observation.challenger_evaluations[candidate_version]
                champion_receipt = observation.challenger_evaluations[champion.version]
                if (
                    _tournament_policy_value(observation, candidate_receipt) is not None
                    and _tournament_policy_value(observation, champion_receipt) is not None
                ):
                    usable.append(observation)
            observed_count = len(resolved)
            usable_count = len(usable)
            availability = usable_count / observed_count if observed_count else 0.0
            state.common_forward_count = usable_count
            deltas: list[float] = []
            candidate_winner_vetoes = 0
            champion_winner_vetoes = 0
            candidate_harm_count = 0
            for observation in usable:
                outcome = observation.checkpoints[primary_key].net_return
                if outcome is None:
                    continue
                candidate_receipt = observation.challenger_evaluations[candidate_version]
                champion_receipt = observation.challenger_evaluations[champion.version]
                candidate_value = _tournament_policy_value(observation, candidate_receipt)
                champion_value = _tournament_policy_value(observation, champion_receipt)
                if candidate_value is None or champion_value is None:
                    continue
                deltas.append(candidate_value - champion_value)
                candidate_winner_vetoes += int(
                    candidate_receipt.proposed_action == "veto" and outcome > 0
                )
                champion_winner_vetoes += int(
                    champion_receipt.proposed_action == "veto" and outcome > 0
                )
                candidate_harm_count += int(candidate_value < champion_value)
            mean_delta = fmean(deltas) if deltas else None
            lower = _mean_lower_bound(deltas, z_score=TOURNAMENT_Z_SCORE)
            upper = _mean_upper_bound(deltas, z_score=TOURNAMENT_Z_SCORE)
            enough = bool(
                usable_count >= TOURNAMENT_MINIMUM_COMMON_OUTCOMES
                and availability >= TOURNAMENT_MINIMUM_AVAILABILITY
            )
            winner_veto_guard = candidate_winner_vetoes <= champion_winner_vetoes + max(
                1, usable_count // 20
            )
            harm_guard = candidate_harm_count <= max(1, int(usable_count * 0.35))
            promoted = bool(
                enough and lower is not None and lower > 0 and winner_veto_guard and harm_guard
            )
            maximum_reached = bool(
                usable_count >= TOURNAMENT_MAXIMUM_COMMON_OUTCOMES
                or observed_count >= TOURNAMENT_MAXIMUM_COMMON_OBSERVED
            )
            inconclusive = bool(
                maximum_reached
                and not promoted
                and (
                    not enough
                    or lower is None
                    or upper is None
                    or (lower <= 0 < upper and winner_veto_guard and harm_guard)
                )
            )
            defended = bool(
                not promoted
                and not inconclusive
                and ((enough and upper is not None and upper <= 0) or maximum_reached)
            )
            settled = inconclusive or defended
            result = (
                "promoted"
                if promoted
                else "inconclusive"
                if inconclusive
                else "rejected"
                if defended
                else "collecting"
            )
            state.last_tournament = {
                "result": result,
                "candidate_version": candidate_version,
                "champion_version": champion.version,
                "common_observed_count": observed_count,
                "common_usable_count": usable_count,
                "availability_fraction": availability,
                "mean_uplift": mean_delta,
                "uplift_lower_bound": lower,
                "uplift_upper_bound": upper,
                "candidate_winner_vetoes": candidate_winner_vetoes,
                "champion_winner_vetoes": champion_winner_vetoes,
                "candidate_harm_count": candidate_harm_count,
                "maximum_common_observed": TOURNAMENT_MAXIMUM_COMMON_OBSERVED,
            }
            if promoted:
                state.champion_version = candidate_version
                state.testing_version = None
                self._append_champion_event(
                    state,
                    kind="promoted",
                    candidate_version=candidate_version,
                    previous_champion_version=champion.version,
                    champion_version=candidate_version,
                    common_observed_count=observed_count,
                    common_usable_count=usable_count,
                    availability_fraction=availability,
                    mean_uplift=mean_delta,
                    uplift_lower_bound=lower,
                )
            elif settled:
                self._append_champion_event(
                    state,
                    kind="inconclusive" if inconclusive else "defended",
                    candidate_version=candidate_version,
                    previous_champion_version=champion.version,
                    champion_version=champion.version,
                    common_observed_count=observed_count,
                    common_usable_count=usable_count,
                    availability_fraction=availability,
                    mean_uplift=mean_delta,
                    uplift_lower_bound=lower,
                )
                if candidate_version not in state.rejected_versions:
                    state.rejected_versions.append(candidate_version)
                    state.rejected_versions = state.rejected_versions[-MAX_MODEL_VERSIONS:]
                state.testing_version = None
            if state.testing_version is None:
                latest = self.skill_artifacts.get(state.latest_candidate_version or "")
                if (
                    latest is not None
                    and latest.qualified
                    and latest.version != state.champion_version
                    and latest.version not in state.rejected_versions
                ):
                    state.testing_version = latest.version
                    state.common_forward_count = 0
            state.updated_at = datetime.now(UTC)
            self.skill_states[key] = state
            self.database.save_challenger_skill_state(state)
            if promoted:
                self._promote_active_skill(candidate, previous_version=champion.version)

    def _current_skill_state(self, skill: ChallengerSkill) -> ChallengerSkillState | None:
        cohort_key = _challenger_cohort_key(
            self.current_risk_mode,
            self.configuration_fingerprint(),
            self.baseline_version(),
            FEATURE_SCHEMA_VERSION,
        )
        return None if cohort_key is None else self.skill_states.get((cohort_key, skill))

    def _skill_activation_candidate(self) -> ChallengerSkillArtifact | None:
        state = self._current_skill_state(ChallengerSkill.ENTRY)
        artifact = (
            self.skill_artifacts.get(state.champion_version or "") if state is not None else None
        )
        return (
            artifact
            if artifact is not None
            and artifact.qualified
            and state is not None
            and state.suspended_version != artifact.version
            and self.entry_outcome_availability()["qualified"]
            else None
        )

    def _activate_skill(self, artifact: ChallengerSkillArtifact) -> None:
        state = self._current_skill_state(artifact.skill)
        if (
            state is None
            or state.champion_version != artifact.version
            or not artifact.qualified
            or state.suspended_version == artifact.version
        ):
            raise ValueError("challenger skill champion is not eligible for activation")
        order = (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        )
        now = datetime.now(UTC)
        # Adding an upstream skill changes the ensemble that every downstream skill observes.
        # Preserve those Champions, but remove their authority until they prove themselves again
        # beside the newly active upstream version.
        for downstream in order[order.index(artifact.skill) + 1 :]:
            old_version = self.active_skill_versions.pop(downstream.value, None)
            downstream_state = self._current_skill_state(downstream)
            if downstream_state is None or old_version is None:
                continue
            downstream_state.active_version = None
            downstream_state.active_dependencies = {}
            downstream_state.last_tournament = {
                **downstream_state.last_tournament,
                "result": "dependency_activated",
                "dependency": artifact.skill.value,
            }
            downstream_state.updated_at = now
            self.database.save_challenger_skill_state(downstream_state)
        self.active_skill_versions[artifact.skill.value] = artifact.version
        state.active_version = artifact.version
        state.active_dependencies = {
            skill: version
            for skill, version in self.active_skill_versions.items()
            if skill != artifact.skill.value
        }
        state.joined_at = now
        state.updated_at = now
        if artifact.skill != ChallengerSkill.ENTRY:
            # Dependencies are recorded in durable state via the join receipt; the immutable
            # artifact remains the exact independently tested object.
            state.last_tournament = {
                **state.last_tournament,
                "joined_with": ",".join(
                    f"{skill}:{version}"
                    for skill, version in sorted(state.active_dependencies.items())
                ),
            }
        self.skill_states[(state.cohort_key, state.skill)] = state
        self.database.save_challenger_skill_state(state)
        self.database.set_setting("active_challenger_skills", self.active_skill_versions)

    def _promote_active_skill(
        self,
        artifact: ChallengerSkillArtifact,
        *,
        previous_version: str,
    ) -> None:
        """Promote a proved champion and make downstream skills re-prove composition."""

        if (
            self.mode != LearningMode.ACTIVE
            or self.active_skill_versions.get(artifact.skill.value) != previous_version
        ):
            return
        order = (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        )
        now = datetime.now(UTC)
        for downstream in order[order.index(artifact.skill) + 1 :]:
            old_version = self.active_skill_versions.pop(downstream.value, None)
            downstream_state = self._current_skill_state(downstream)
            if downstream_state is None or old_version is None:
                continue
            downstream_state.active_version = None
            downstream_state.active_dependencies = {}
            downstream_state.last_tournament = {
                **downstream_state.last_tournament,
                "result": "dependency_promoted",
                "dependency": artifact.skill.value,
            }
            downstream_state.updated_at = now
            self.database.save_challenger_skill_state(downstream_state)
        self._activate_skill(artifact)

    def _deactivate_all_skills(self) -> None:
        for state in self.skill_states.values():
            if state.active_version is None:
                continue
            state.active_version = None
            state.active_dependencies = {}
            state.updated_at = datetime.now(UTC)
            self.database.save_challenger_skill_state(state)
        self.active_skill_versions = {}
        self.database.set_setting("active_challenger_skills", {})

    def _restore_active_skill_versions(self) -> None:
        if self.mode != LearningMode.ACTIVE:
            self.active_skill_versions = {}
            return
        requested = dict(self.active_skill_versions)
        restored: dict[str, str] = {}
        dependency_broken = False
        for skill in (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        ):
            version = requested.get(skill.value)
            if version is None:
                continue
            if dependency_broken:
                continue
            artifact = self.skill_artifacts.get(version)
            state = self._current_skill_state(skill)
            if (
                artifact is None
                or state is None
                or not artifact.qualified
                or artifact.version != state.active_version
                or state.suspended_version == artifact.version
                or any(
                    restored.get(dependency) != dependency_version
                    for dependency, dependency_version in state.active_dependencies.items()
                )
            ):
                dependency_broken = True
                continue
            restored[skill.value] = version
        # Entry is the root permission. A partially written or corrupted active map must
        # never restore a downstream skill on its own after restart.
        if ChallengerSkill.ENTRY.value not in restored:
            restored = {}
        for state in self.skill_states.values():
            if state.active_version is None:
                continue
            if restored.get(state.skill.value) == state.active_version:
                continue
            state.active_version = None
            state.active_dependencies = {}
            state.updated_at = datetime.now(UTC)
            self.database.save_challenger_skill_state(state)
        self.active_skill_versions = restored
        self.database.set_setting("active_challenger_skills", restored)

    def _skill_health(
        self,
        skill: ChallengerSkill,
        version: str,
    ) -> dict[str, Any]:
        artifact = self.skill_artifacts.get(version)
        if artifact is None:
            return {
                "state": "suspended",
                "model_version": version,
                "observed_count": 0,
                "usable_count": 0,
                "availability_fraction": 0.0,
                "estimated_uplift": None,
                "uplift_upper_bound": None,
                "suspension_reason": "artifact_unavailable",
            }
        observed: list[LearningObservation] = []
        for observation in sorted(self.observations.values(), key=lambda item: item.created_at):
            if (
                observation.risk_mode != artifact.risk_mode
                or observation.configuration_fingerprint != artifact.configuration_fingerprint
                or observation.baseline_version != artifact.baseline_version
                or observation.active_skill_versions.get(skill.value) != version
                or observation.baseline_action != DecisionAction.ENTER
                or not observation.baseline_actionable
                or version not in observation.challenger_evaluations
                or not self._upstream_skills_supported(observation, skill)
            ):
                continue
            if not _skill_receipt_outcome_resolved(
                observation,
                observation.challenger_evaluations[version],
            ):
                continue
            observed.append(observation)
        observed = observed[-ACTIVE_HEALTH_WINDOW:]
        deltas: list[float] = []
        for observation in observed:
            receipt = observation.challenger_evaluations[version]
            actual = _tournament_policy_value(observation, receipt)
            baseline = _skill_baseline_value(observation, skill)
            if actual is not None and baseline is not None:
                deltas.append(actual - baseline)
        observed_count = len(observed)
        usable_count = len(deltas)
        availability = usable_count / observed_count if observed_count else 0.0
        uplift = fmean(deltas) if deltas else None
        upper = _mean_upper_bound(deltas, z_score=ACTIVE_HEALTH_Z_SCORE)
        enough = bool(
            usable_count >= ACTIVE_HEALTH_MINIMUM_SAMPLES
            and availability >= ACTIVE_HEALTH_MINIMUM_AVAILABILITY
        )
        unverifiable = bool(
            observed_count >= ACTIVE_HEALTH_MINIMUM_SAMPLES
            and availability < ACTIVE_HEALTH_MINIMUM_AVAILABILITY
        )
        degraded = bool(enough and upper is not None and upper < -ACTIVE_HEALTH_HARM_MARGIN)
        return {
            "state": (
                "unverifiable"
                if unverifiable
                else "degraded"
                if degraded
                else "healthy"
                if enough
                else "collecting"
            ),
            "model_version": version,
            "observed_count": observed_count,
            "usable_count": usable_count,
            "minimum_samples": ACTIVE_HEALTH_MINIMUM_SAMPLES,
            "availability_fraction": availability,
            "estimated_uplift": uplift,
            "uplift_upper_bound": upper,
        }

    def _upstream_skills_supported(
        self,
        observation: LearningObservation,
        skill: ChallengerSkill,
    ) -> bool:
        order = (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        )
        for upstream in order[: order.index(skill)]:
            version = observation.active_skill_versions.get(upstream.value)
            if version is None:
                continue
            receipt = observation.challenger_evaluations.get(version)
            if receipt is None:
                return False
            if upstream in {ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION} and (
                receipt.proposed_action == "veto"
            ):
                return False
        return True

    def _skill_join_evidence(
        self,
        artifact: ChallengerSkillArtifact,
    ) -> dict[str, Any]:
        observed: list[LearningObservation] = []
        for observation in sorted(self.observations.values(), key=lambda item: item.created_at):
            if (
                observation.created_at <= artifact.created_at
                or observation.risk_mode != artifact.risk_mode
                or observation.configuration_fingerprint != artifact.configuration_fingerprint
                or observation.baseline_version != artifact.baseline_version
                or observation.baseline_action != DecisionAction.ENTER
                or not observation.baseline_actionable
                or artifact.version not in observation.challenger_evaluations
                or any(
                    observation.active_skill_versions.get(skill) != version
                    for skill, version in self.active_skill_versions.items()
                )
                or not self._upstream_skills_supported(observation, artifact.skill)
            ):
                continue
            if not _skill_receipt_outcome_resolved(
                observation,
                observation.challenger_evaluations[artifact.version],
            ):
                continue
            observed.append(observation)
        deltas: list[float] = []
        harm_count = 0
        for observation in observed:
            candidate_value = _tournament_policy_value(
                observation,
                observation.challenger_evaluations[artifact.version],
            )
            baseline_value = _skill_baseline_value(observation, artifact.skill)
            if candidate_value is None or baseline_value is None:
                continue
            delta = candidate_value - baseline_value
            deltas.append(delta)
            harm_count += int(delta < 0)
        availability = len(deltas) / len(observed) if observed else 0.0
        lower = _mean_lower_bound(deltas, z_score=TOURNAMENT_Z_SCORE)
        harm_fraction = harm_count / len(deltas) if deltas else 0.0
        ready = bool(
            len(deltas) >= TOURNAMENT_MINIMUM_COMMON_OUTCOMES
            and availability >= TOURNAMENT_MINIMUM_AVAILABILITY
            and lower is not None
            and lower > 0
            and harm_fraction <= SIZING_MAXIMUM_HARM_FRACTION
        )
        return {
            "ready": ready,
            "observed_count": len(observed),
            "usable_count": len(deltas),
            "availability_fraction": availability,
            "mean_uplift": fmean(deltas) if deltas else None,
            "uplift_lower_bound": lower,
            "harm_count": harm_count,
            "harm_fraction": harm_fraction,
        }

    def _suspend_skill(self, skill: ChallengerSkill, reason: str) -> None:
        order = (
            ChallengerSkill.ENTRY,
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        )
        now = datetime.now(UTC)
        for affected in order[order.index(skill) :]:
            version = self.active_skill_versions.pop(affected.value, None)
            state = self._current_skill_state(affected)
            if state is None or version is None:
                continue
            state.active_version = None
            state.active_dependencies = {}
            if affected == skill:
                state.suspended_version = version
                state.suspension_reason = reason
                state.suspended_at = now
            else:
                state.last_tournament = {
                    **state.last_tournament,
                    "result": "dependency_deactivated",
                    "dependency": skill.value,
                }
            state.updated_at = now
            self.database.save_challenger_skill_state(state)
        self.database.set_setting("active_challenger_skills", self.active_skill_versions)
        if ChallengerSkill.ENTRY.value not in self.active_skill_versions:
            self.mode = LearningMode.SHADOW
            self.database.set_setting("learning_mode", self.mode.value)

    def _govern_skill_ensemble(self) -> None:
        if not self.consent_granted or self.mode != LearningMode.ACTIVE:
            return
        for skill_name, version in list(self.active_skill_versions.items()):
            try:
                skill = ChallengerSkill(skill_name)
            except ValueError:
                self.active_skill_versions.pop(skill_name, None)
                continue
            health = self._skill_health(skill, version)
            if health["state"] in {"degraded", "unverifiable", "suspended"}:
                self._suspend_skill(skill, str(health["state"]))
                return
        if ChallengerSkill.ENTRY.value not in self.active_skill_versions:
            entry = self._skill_activation_candidate()
            if entry is not None:
                self._activate_skill(entry)
            return
        for skill in (
            ChallengerSkill.MANIPULATION,
            ChallengerSkill.SIZING,
            ChallengerSkill.EXIT,
        ):
            if skill.value in self.active_skill_versions:
                continue
            state = self._current_skill_state(skill)
            artifact = (
                self.skill_artifacts.get(state.champion_version or "")
                if state is not None
                else None
            )
            if (
                state is None
                or artifact is None
                or not artifact.qualified
                or state.suspended_version == artifact.version
            ):
                continue
            join = self._skill_join_evidence(artifact)
            state.last_tournament = {**state.last_tournament, **join, "result": "join_proof"}
            state.updated_at = datetime.now(UTC)
            self.database.save_challenger_skill_state(state)
            if join["ready"]:
                self._activate_skill(artifact)
                return

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

    def _new_outcomes_since_model(self, model: LearningModel) -> int:
        """Count newly resolved outcomes only inside the model's exact learning cohort."""

        key = str(PRIMARY_HORIZON_SECONDS)
        return sum(
            observation.checkpoints[key].observed_at > model.created_at
            for observation, _ in self._training_rows(
                mode=model.risk_mode,
                configuration_fingerprint=model.configuration_fingerprint,
                match_configuration=True,
            )
        )

    def _retrain_if_ready(
        self,
        *,
        target_mode: RiskMode | None = None,
        target_configuration: str | None = None,
    ) -> None:
        self._govern_active_model()
        all_rows = self._training_rows()
        self.outcomes_seen = max(self.outcomes_seen, len(all_rows))
        if not all_rows:
            return
        if target_mode is None:
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
        if latest is not None and self._new_outcomes_since_model(latest) < RETRAIN_SAMPLE_INTERVAL:
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
        baseline_versions = {observation.baseline_version for observation, _ in rows}
        feature_schemas = {observation.feature_schema_version for observation, _ in rows}
        if len(baseline_versions) == 1 and feature_schemas == {FEATURE_SCHEMA_VERSION}:
            baseline_version = next(iter(baseline_versions))
            self._publish_entry_artifact(
                model,
                baseline_version=baseline_version,
                evidence_started_at=rows[0][0].created_at,
                evidence_ended_at=rows[-1][0].created_at,
            )
            self._publish_manipulation_artifact(
                risk_mode=target_mode,
                configuration_fingerprint=target_configuration,
                baseline_version=baseline_version,
                rows=rows,
                training=training,
                validation=validation,
                resolved_count=len(resolved),
                embargoed_count=len(raw_training) - len(training),
            )
            self._publish_sizing_artifact(
                risk_mode=target_mode,
                configuration_fingerprint=target_configuration,
                baseline_version=baseline_version,
                rows=rows,
                training=training,
                validation=validation,
                embargoed_count=len(raw_training) - len(training),
            )
            self._publish_exit_artifact(
                risk_mode=target_mode,
                configuration_fingerprint=target_configuration,
                baseline_version=baseline_version,
            )
            self._advance_entry_tournaments()
        self._prune_model_history()
        self._govern_active_model()

    def context_outcomes_seen(
        self,
        risk_mode: RiskMode,
        configuration_fingerprint: str | None,
        baseline_version: str,
        feature_schema_version: str,
        dependency_versions: dict[str, str],
    ) -> int:
        return self.context_outcome_counts.get(
            _coach_outcome_context_key(
                risk_mode,
                configuration_fingerprint,
                baseline_version,
                feature_schema_version,
                dependency_versions,
            ),
            0,
        )

    def _record_usable_outcome(self, observation: LearningObservation) -> None:
        self.outcomes_seen += 1
        self.database.set_setting("learning_outcomes_seen", self.outcomes_seen)
        context_key = _coach_outcome_context_key(
            observation.risk_mode,
            observation.configuration_fingerprint,
            observation.baseline_version,
            observation.feature_schema_version,
            observation.active_skill_versions,
        )
        self.context_outcome_counts[context_key] = (
            self.context_outcome_counts.get(context_key, 0) + 1
        )
        self.database.set_setting("learning_context_outcomes_seen", self.context_outcome_counts)

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
        skill_removed = set(self.database.prune_challenger_artifacts(MAX_MODEL_VERSIONS))
        if skill_removed:
            self.skill_artifacts = {
                version: artifact
                for version, artifact in self.skill_artifacts.items()
                if version not in skill_removed
            }

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


def _mean_upper_bound(values: list[float], *, z_score: float) -> float | None:
    if not values:
        return None
    mean = fmean(values)
    if len(values) < 2:
        return mean
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean + z_score * math.sqrt(variance / len(values))


def _size_trial_key(multiplier: float) -> str:
    return f"{multiplier:g}"


def _nearest_size_multiplier(value: float) -> float:
    finite = value if math.isfinite(value) else 1.0
    return min(SIZING_MULTIPLIERS, key=lambda candidate: (abs(candidate - finite), candidate))


def _coach_policy_is_allowlisted(hypothesis: CoachHypothesis) -> bool:
    """Revalidate Coach output at the Challenger authority boundary.

    Persisted Coach research is untrusted input here. Only deterministic policies
    that the local candidate generator could have produced may enter a tournament.
    """

    conditions = tuple(
        (condition.feature_name, condition.operator, condition.threshold)
        for condition in hypothesis.conditions
    )
    if hypothesis.kind == CoachExperimentKind.ENTRY_VETO:
        return (
            hypothesis.skill == ChallengerSkill.ENTRY
            and len(conditions) == 1
            and conditions[0] in COACH_ENTRY_RULES
            and hypothesis.size_multiplier is None
            and hypothesis.hold_seconds is None
            and hypothesis.baseline_hold_seconds is None
        )
    if hypothesis.kind == CoachExperimentKind.MANIPULATION_VETO:
        return (
            hypothesis.skill == ChallengerSkill.MANIPULATION
            and (
                (len(conditions) == 1 and conditions[0] in COACH_MANIPULATION_RULES)
                or conditions in COACH_MANIPULATION_COMBINATIONS
            )
            and hypothesis.size_multiplier is None
            and hypothesis.hold_seconds is None
            and hypothesis.baseline_hold_seconds is None
        )
    if hypothesis.kind == CoachExperimentKind.SIZING_MULTIPLIER:
        return (
            hypothesis.skill == ChallengerSkill.SIZING
            and not conditions
            and hypothesis.size_multiplier in SIZING_MULTIPLIERS
            and hypothesis.size_multiplier != 1.0
            and hypothesis.hold_seconds is None
            and hypothesis.baseline_hold_seconds is None
        )
    if hypothesis.kind == CoachExperimentKind.EARLIER_REVIEW:
        return (
            hypothesis.skill == ChallengerSkill.EXIT
            and not conditions
            and hypothesis.size_multiplier is None
            and hypothesis.hold_seconds in LEARNING_HORIZONS_SECONDS
            and hypothesis.baseline_hold_seconds in LEARNING_HORIZONS_SECONDS
            and hypothesis.hold_seconds < hypothesis.baseline_hold_seconds
        )
    return False


def _size_trial_value(
    observation: LearningObservation,
    multiplier: float,
    *,
    horizon: int = PRIMARY_HORIZON_SECONDS,
) -> float | None:
    trial = observation.size_trials.get(_size_trial_key(multiplier))
    baseline = observation.size_trials.get(_size_trial_key(1.0))
    if (
        trial is None
        or baseline is None
        or not trial.eligible_at_entry
        or trial.entry_cost_lamports is None
        or baseline.entry_cost_lamports is None
        or baseline.entry_cost_lamports <= 0
    ):
        return None
    checkpoint = trial.checkpoints.get(str(horizon))
    if checkpoint is None or checkpoint.exit_value_lamports is None:
        return None
    return (checkpoint.exit_value_lamports - trial.entry_cost_lamports) / (
        baseline.entry_cost_lamports
    )


def _best_size_multiplier(observation: LearningObservation) -> float | None:
    values = [
        (multiplier, value)
        for multiplier in SIZING_MULTIPLIERS
        if (value := _size_trial_value(observation, multiplier)) is not None
    ]
    if not values:
        return None
    return max(values, key=lambda item: (item[1], -abs(item[0] - 1.0)))[0]


def _tournament_policy_value(
    observation: LearningObservation,
    receipt: ChallengerEvaluationReceipt,
) -> float | None:
    if receipt.skill == ChallengerSkill.SIZING:
        try:
            multiplier = float(receipt.proposed_action)
        except ValueError:
            return None
        return _size_trial_value(observation, multiplier)
    if receipt.skill == ChallengerSkill.EXIT:
        try:
            horizon = int(receipt.proposed_action)
        except ValueError:
            return None
        checkpoint = observation.checkpoints.get(str(horizon))
        return None if checkpoint is None else checkpoint.net_return
    checkpoint = observation.checkpoints.get(str(PRIMARY_HORIZON_SECONDS))
    if checkpoint is None or checkpoint.net_return is None:
        return None
    return checkpoint.net_return if receipt.proposed_action == "support" else 0.0


def _skill_receipt_outcome_resolved(
    observation: LearningObservation,
    receipt: ChallengerEvaluationReceipt,
) -> bool:
    """Distinguish an outcome still unfolding from a resolved unavailable outcome."""

    if receipt.skill == ChallengerSkill.EXIT:
        try:
            selected_horizon = int(receipt.proposed_action)
        except ValueError:
            return True
        baseline_horizon = RISK_LIMITS[observation.risk_mode].max_hold_seconds
        return all(
            str(horizon) in observation.checkpoints
            for horizon in {selected_horizon, baseline_horizon}
        )
    return str(PRIMARY_HORIZON_SECONDS) in observation.checkpoints


def _skill_baseline_value(
    observation: LearningObservation,
    skill: ChallengerSkill,
) -> float | None:
    if skill == ChallengerSkill.SIZING:
        return _size_trial_value(observation, 1.0)
    if skill == ChallengerSkill.EXIT:
        checkpoint = observation.checkpoints.get(
            str(RISK_LIMITS[observation.risk_mode].max_hold_seconds)
        )
        return None if checkpoint is None else checkpoint.net_return
    checkpoint = observation.checkpoints.get(str(PRIMARY_HORIZON_SECONDS))
    return None if checkpoint is None else checkpoint.net_return


def _challenger_cohort_key(
    risk_mode: RiskMode,
    configuration_fingerprint: str | None,
    baseline_version: str,
    feature_schema_version: str,
) -> str | None:
    if not configuration_fingerprint:
        return None
    material = "\n".join(
        (
            risk_mode.value,
            configuration_fingerprint,
            baseline_version,
            feature_schema_version,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _skill_artifact_parts(
    artifact: ChallengerSkillArtifact,
) -> tuple[list[float], list[float], list[float]] | None:
    try:
        means = [float(value) for value in artifact.parameters["means"]]
        scales = [float(value) for value in artifact.parameters["scales"]]
        coefficients = [float(value) for value in artifact.parameters["coefficients"]]
    except (KeyError, TypeError, ValueError):
        return None
    width = len(artifact.feature_names)
    if (
        tuple(artifact.feature_names)
        not in {FEATURE_NAMES, MANIPULATION_FEATURE_NAMES, SIZING_FEATURE_NAMES}
        or len(means) != width
        or len(scales) != width
        or len(coefficients) != width + 1
        or any(not math.isfinite(value) for value in means)
        or any(not math.isfinite(value) or value <= 0 for value in scales)
        or any(not math.isfinite(value) for value in coefficients)
    ):
        return None
    return means, scales, coefficients


def _predict_skill_artifact(
    artifact: ChallengerSkillArtifact,
    features: dict[str, float],
) -> float | None:
    coach_policy = artifact.parameters.get("coach_policy")
    if isinstance(coach_policy, dict):
        kind = str(coach_policy.get("kind") or "")
        if kind == "sizing_multiplier":
            raw_multiplier = coach_policy.get("size_multiplier")
            if raw_multiplier is None:
                return None
            try:
                multiplier = float(raw_multiplier)
            except (TypeError, ValueError):
                return None
            return multiplier if multiplier in SIZING_MULTIPLIERS else None
        conditions = coach_policy.get("conditions", [])
        if not isinstance(conditions, list):
            return None
        matches = True
        for condition in conditions:
            if not isinstance(condition, dict):
                return None
            name = condition.get("feature_name")
            operator = condition.get("operator")
            threshold = condition.get("threshold")
            if not isinstance(name, str) or operator not in {"<=", ">="}:
                return None
            value = features.get(name)
            if threshold is None:
                return None
            try:
                limit = float(threshold)
            except (TypeError, ValueError):
                return None
            if value is None or not math.isfinite(value) or not math.isfinite(limit):
                return None
            matches = matches and (value <= limit if operator == "<=" else value >= limit)
        return -1.0 if matches else 1.0
    parts = _skill_artifact_parts(artifact)
    return (
        None
        if parts is None
        else _predict_named_parts(parts, features, tuple(artifact.feature_names))
    )


def _within_skill_artifact_support(
    artifact: ChallengerSkillArtifact,
    features: dict[str, float],
) -> bool:
    coach_policy = artifact.parameters.get("coach_policy")
    if isinstance(coach_policy, dict):
        kind = str(coach_policy.get("kind") or "")
        if kind == "sizing_multiplier":
            return _predict_skill_artifact(artifact, features) is not None
        conditions = coach_policy.get("conditions", [])
        return bool(
            isinstance(conditions, list)
            and conditions
            and all(
                isinstance(condition, dict)
                and isinstance(condition.get("feature_name"), str)
                and condition["feature_name"] in features
                and math.isfinite(features[condition["feature_name"]])
                for condition in conditions
            )
        )
    parts = _skill_artifact_parts(artifact)
    return bool(
        parts is not None
        and _within_named_parts_support(parts, features, tuple(artifact.feature_names))
    )


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
    *,
    feature_names: tuple[str, ...] = FEATURE_NAMES,
) -> tuple[list[float], list[float], list[float]] | None:
    if not rows:
        return None
    raw = [[item.features.get(name, 0.0) for name in feature_names] for item, _ in rows]
    outcomes = [max(-1.0, min(3.0, outcome)) for _, outcome in rows]
    weights = [0.5 ** ((len(rows) - 1 - index) / 500) for index in range(len(rows))]
    weight_sum = sum(weights)
    means = [
        sum(weight * row[index] for weight, row in zip(weights, raw, strict=True)) / weight_sum
        for index in range(len(feature_names))
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
    width = len(feature_names) + 1
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
    return _within_named_parts_support(model, features, FEATURE_NAMES)


def _within_named_parts_support(
    model: tuple[list[float], list[float], list[float]],
    features: dict[str, float],
    feature_names: tuple[str, ...],
) -> bool:
    means, scales, _ = model
    if (
        len(means) != len(feature_names)
        or len(scales) != len(feature_names)
        or any(not math.isfinite(value) for value in means)
        or any(not math.isfinite(value) or value <= 0 for value in scales)
    ):
        return False
    return all(
        abs((features.get(name, 0.0) - mean) / max(scale, 1e-6)) <= MODEL_SUPPORT_Z_SCORE
        for name, mean, scale in zip(feature_names, means, scales, strict=True)
    )


def _predict_parts(
    model: tuple[list[float], list[float], list[float]],
    features: dict[str, float],
) -> float:
    return _predict_named_parts(model, features, FEATURE_NAMES)


def _predict_named_parts(
    model: tuple[list[float], list[float], list[float]],
    features: dict[str, float],
    feature_names: tuple[str, ...],
) -> float:
    means, scales, coefficients = model
    prediction = coefficients[0]
    for index, name in enumerate(feature_names):
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


def _skill_artifact_summary(
    artifact: ChallengerSkillArtifact | None,
) -> dict[str, Any] | None:
    if artifact is None:
        return None
    return {
        "version": artifact.version,
        "created_at": artifact.created_at.isoformat(),
        "skill": artifact.skill.value,
        "outcomes_seen": artifact.outcomes_seen,
        "sample_count": artifact.sample_count,
        "training_count": artifact.training_count,
        "validation_count": artifact.validation_count,
        "embargoed_count": artifact.embargoed_count,
        "qualified": artifact.qualified,
        "metrics": dict(artifact.metrics),
        "parameters": dict(artifact.parameters),
    }


def _skill_qualification_gates(
    skill: ChallengerSkill,
    artifact: ChallengerSkillArtifact | None,
) -> list[dict[str, Any]]:
    def number(name: str) -> float | None:
        if artifact is None:
            return None
        value = artifact.metrics.get(name)
        return (
            float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
        )

    def gate(
        gate_id: str,
        label: str,
        current: float | int | bool | None,
        target: float | int | bool,
        comparison: str,
        passed: bool,
        unit: str,
    ) -> dict[str, Any]:
        return {
            "id": f"{skill.value}_{gate_id}",
            "label": label,
            "current": current,
            "target": target,
            "comparison": comparison,
            "state": "passed" if passed else "collecting" if current is None else "not_met",
            "unit": unit,
            "detail": "Server-authoritative, chronological proof for this skill only.",
        }

    if artifact is None:
        return [
            gate(
                "samples",
                "Forward evidence",
                None,
                HOLD_TIMING_MINIMUM_SAMPLES
                if skill == ChallengerSkill.EXIT
                else MINIMUM_TRAINING_SAMPLES,
                ">=",
                False,
                "count",
            )
        ]
    specifications: tuple[tuple[str, str, float | int, str, str], ...]
    if skill == ChallengerSkill.ENTRY:
        return [
            gate(
                "qualified",
                "Independent proof",
                artifact.qualified,
                True,
                "=",
                artifact.qualified,
                "boolean",
            )
        ]
    if skill == ChallengerSkill.MANIPULATION:
        specifications = (
            ("outcome_availability", "Executable coverage", 0.70, ">=", "fraction"),
            ("in_distribution_fraction", "Familiar evidence", 0.90, ">=", "fraction"),
            ("policy_samples", "Policy outcomes", 20, ">=", "count"),
            ("policy_vetoes", "Tested vetoes", 5, ">=", "count"),
            ("policy_uplift_lower", "Conservative value", 0.0, ">", "fraction"),
            (
                "policy_winner_veto_fraction",
                "Winner veto rate",
                0.35,
                "<=",
                "fraction",
            ),
        )
    elif skill == ChallengerSkill.SIZING:
        specifications = (
            ("outcome_availability", "Executable coverage", 0.70, ">=", "fraction"),
            ("in_distribution_fraction", "Familiar evidence", 0.90, ">=", "fraction"),
            ("policy_samples", "Policy outcomes", 20, ">=", "count"),
            ("policy_changes", "Tested size changes", 5, ">=", "count"),
            ("uplift_lower_bound", "Conservative value", 0.0, ">", "fraction"),
            ("harm_fraction", "Harm rate", 0.35, "<=", "fraction"),
        )
    else:
        specifications = (
            (
                "validation_availability_fraction",
                "Executable coverage",
                0.70,
                ">=",
                "fraction",
            ),
            (
                "validation_uplift_lower_bound",
                "Conservative timing value",
                0.01,
                ">=",
                "fraction",
            ),
        )
    gates: list[dict[str, Any]] = []
    for gate_id, label, target, comparison, unit in specifications:
        current = number(gate_id)
        passed = bool(
            current is not None
            and (
                current <= target
                if comparison == "<="
                else current > target
                if comparison == ">"
                else current >= target
            )
        )
        gates.append(gate(gate_id, label, current, target, comparison, passed, unit))
    gates.append(
        gate(
            "qualified",
            "Independent proof",
            artifact.qualified,
            True,
            "=",
            artifact.qualified,
            "boolean",
        )
    )
    return gates


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
