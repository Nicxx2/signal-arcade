from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class EventKind(StrEnum):
    CREATE = "create"
    TRADE = "trade"
    COMPLETE = "complete"
    MIGRATE = "migrate"
    MARKET = "market"
    HEALTH = "health"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class DecisionAction(StrEnum):
    ENTER = "enter"
    WATCH = "watch"
    PASS = "pass"  # noqa: S105 -- decision action, not a credential
    ABSTAIN = "abstain"


class ExitAction(StrEnum):
    HOLD = "hold"
    WAIT = "wait"
    EXIT = "exit"


class PositionMarketStatus(StrEnum):
    """Whether an open paper position currently has an executable valuation route."""

    ACTIVE = "active"
    EXIT_BLOCKED = "exit_blocked"
    DORMANT = "dormant"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskMode(StrEnum):
    SAFE = "safe"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class QuoteCurrency(StrEnum):
    SOL = "SOL"
    USDC = "USDC"


class LearningMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ACTIVE = "active"


class AiDecisionMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    GUARDED = "guarded"


class AiCriticVerdict(StrEnum):
    SUPPORT = "support"
    VETO = "veto"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class LearningObservationStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"


class CoachExperimentKind(StrEnum):
    ENTRY_VETO = "entry_veto"
    EARLIER_REVIEW = "earlier_review"


class CoachExperimentState(StrEnum):
    TESTING = "testing"
    PROMISING = "promising"
    INCONCLUSIVE = "inconclusive"
    NOT_SUPPORTED = "not_supported"


class DataValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | int | str | bool | None
    unit: str
    as_of: datetime
    sources: list[str]
    freshness_seconds: float = Field(ge=0)
    quality: float = Field(ge=0, le=1)
    missing_reason: str | None = None


class MarketEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    source: str
    kind: EventKind
    mint: str | None = None
    signature: str | None = None
    slot: int | None = Field(default=None, ge=0)
    block_time: datetime | None = None
    received_at: datetime = Field(default_factory=utc_now)
    schema_version: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mint: str
    symbol: str
    name: str
    venue: str
    computed_at: datetime = Field(default_factory=utc_now)
    values: dict[str, DataValue]
    data_confidence: float = Field(ge=0, le=1)
    hard_flags: list[str] = Field(default_factory=list)

    def number(self, key: str, default: float = 0.0) -> float:
        item = self.values.get(key)
        if item is None or item.value is None or isinstance(item.value, bool):
            return default
        try:
            return float(item.value)
        except (TypeError, ValueError):
            return default


class DecisionScore(BaseModel):
    opportunity: float = Field(ge=0, le=1)
    danger: float = Field(ge=0, le=1)
    execution: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    net_edge_index: float = Field(
        validation_alias=AliasChoices("net_edge_index", "expected_net_return")
    )
    composite: int = Field(ge=0, le=100)


class LearningAssessment(BaseModel):
    model_version: str
    predicted_net_return: float = Field(ge=-1, le=10)
    conservative_net_return: float = Field(ge=-1, le=10)
    validation_rmse: float = Field(ge=0)
    applied: bool = False
    verdict: str


class ExitAssessment(BaseModel):
    """Latest transparent, persisted explanation for an open-position action."""

    policy_version: str = "adaptive-exit-v1"
    evaluated_at: datetime
    action: ExitAction
    reason: str
    support_score: float = Field(ge=0, le=1)
    pnl_fraction: float = Field(ge=-1, le=10)
    peak_return_fraction: float = Field(ge=-1, le=10)
    drawdown_from_peak_fraction: float = Field(ge=0, le=1)
    age_seconds: float = Field(ge=0)
    soft_hold_seconds: int = Field(gt=0)
    hard_hold_seconds: int = Field(gt=0)
    evidence: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    mint: str
    symbol: str
    created_at: datetime = Field(default_factory=utc_now)
    action: DecisionAction
    risk_mode: RiskMode
    score: DecisionScore
    reasons: list[str]
    blockers: list[str]
    feature_snapshot: FeatureSnapshot
    model_version: str = "baseline-v1"
    planned_order_size_sol: float | None = Field(default=None, gt=0)
    learning_assessment: LearningAssessment | None = None
    season_id: str | None = None
    configuration_fingerprint: str | None = None


class LearningCheckpoint(BaseModel):
    horizon_seconds: int = Field(gt=0)
    observed_at: datetime
    net_return: float | None = Field(default=None, ge=-1, le=10)
    exit_value_lamports: int | None = Field(default=None, ge=0)
    missing_reason: str | None = None


class LearningObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    decision_id: str
    mint: str
    symbol: str
    created_at: datetime
    baseline_action: DecisionAction
    risk_mode: RiskMode
    baseline_edge_index: float
    baseline_composite: int = Field(ge=0, le=100)
    features: dict[str, float]
    token_units: int = Field(gt=0)
    entry_cost_lamports: int = Field(gt=0)
    entry_price_impact_fraction: float = Field(ge=0, le=1)
    fee_bps: int = Field(ge=0, le=10_000)
    checkpoints: dict[str, LearningCheckpoint] = Field(default_factory=dict)
    status: LearningObservationStatus = LearningObservationStatus.PENDING
    source_mode: str = "solana_mainnet"
    # Frozen at decision time for genuinely prequential monitoring. These defaults keep
    # observations written before the live-health guard fully readable.
    evaluation_model_version: str | None = None
    evaluation_prediction: float | None = Field(default=None, ge=-1, le=10)
    evaluation_validation_rmse: float | None = Field(default=None, ge=0)
    # Whether the deterministic broker could actually have submitted this baseline ENTER. This
    # is saved in Shadow too, so a future challenger is judged on the veto-only policy it would
    # deploy rather than only on broad candidate ranking.
    baseline_actionable: bool = False
    evaluation_actionable: bool = False
    # Compact durable audit context survives pruning of bulky non-entry decisions.
    baseline_reasons: list[str] = Field(default_factory=list)
    baseline_blockers: list[str] = Field(default_factory=list)
    opportunity_score: float | None = Field(default=None, ge=0, le=1)
    danger_score: float | None = Field(default=None, ge=0, le=1)
    execution_score: float | None = Field(default=None, ge=0, le=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    season_id: str | None = None
    configuration_fingerprint: str | None = None


class LearningModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    created_at: datetime = Field(default_factory=utc_now)
    # Monotonic count of usable outcomes seen, independent of the bounded training window.
    outcomes_seen: int = Field(default=0, ge=0)
    risk_mode: RiskMode | None = None
    configuration_fingerprint: str | None = None
    sample_count: int = Field(ge=0)
    resolved_count: int = Field(default=0, ge=0)
    outcome_availability_fraction: float = Field(default=1.0, ge=0, le=1)
    training_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    embargoed_count: int = Field(default=0, ge=0)
    feature_names: list[str]
    means: list[float]
    scales: list[float]
    coefficients: list[float]
    validation_rmse: float = Field(ge=0)
    naive_rmse: float = Field(ge=0)
    learner_correlation: float = Field(ge=-1, le=1)
    baseline_correlation: float = Field(ge=-1, le=1)
    learner_top_mean_return: float = Field(ge=-1, le=10)
    baseline_top_mean_return: float = Field(ge=-1, le=10)
    overall_mean_return: float = Field(ge=-1, le=10)
    validation_in_distribution_fraction: float = Field(default=0.0, ge=0, le=1)
    policy_validation_count: int = Field(default=0, ge=0)
    policy_veto_count: int = Field(default=0, ge=0)
    policy_winner_veto_count: int = Field(default=0, ge=0)
    policy_mean_uplift: float | None = Field(default=None, ge=-10, le=10)
    policy_uplift_lower_bound: float | None = Field(default=None, ge=-10, le=10)
    qualified: bool = False


class AiCriticAssessment(BaseModel):
    """Immutable local-LLM recommendation plus its later paper counterfactual."""

    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    decision_id: str
    mint: str
    symbol: str
    created_at: datetime = Field(default_factory=utc_now)
    snapshot_at: datetime
    mode: AiDecisionMode
    applied: bool = False
    model_name: str
    model_digest: str
    prompt_version: str
    schema_version: str
    input_sha256: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = Field(ge=0)
    valid: bool
    invalid_reason: str | None = None
    verdict: AiCriticVerdict | None = None
    confidence: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    summary: str = ""
    baseline_action: DecisionAction
    token_units: int | None = Field(default=None, gt=0)
    entry_cost_lamports: int | None = Field(default=None, gt=0)
    fee_bps: int | None = Field(default=None, ge=0, le=10_000)
    outcome_due_at: datetime | None = None
    outcome_net_return: float | None = Field(default=None, ge=-1, le=10)
    counterfactual_uplift: float | None = Field(default=None, ge=-10, le=10)
    outcome_missing_reason: str | None = None
    resolved_at: datetime | None = None
    season_id: str | None = None
    configuration_fingerprint: str | None = None


class CoachReview(BaseModel):
    """One bounded local-AI selection from deterministic coaching candidates."""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    created_at: datetime = Field(default_factory=utc_now)
    cutoff_at: datetime
    outcomes_seen: int = Field(ge=0)
    risk_mode: RiskMode
    configuration_fingerprint: str
    model_name: str
    model_digest: str = ""
    prompt_version: str
    schema_version: str
    input_sha256: str
    candidate_count: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    valid: bool
    selected_candidate_id: str | None = None
    summary: str = Field(default="", max_length=240)
    failure_reason: str | None = Field(default=None, max_length=120)


class CoachHypothesis(BaseModel):
    """A zero-influence experiment measured only on outcomes created after its cutoff."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    signature: str
    coach_review_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    cutoff_at: datetime
    kind: CoachExperimentKind
    state: CoachExperimentState = CoachExperimentState.TESTING
    title: str = Field(max_length=120)
    rationale: str = Field(max_length=240)
    risk_mode: RiskMode
    configuration_fingerprint: str
    model_name: str
    model_digest: str = ""
    feature_name: str | None = None
    operator: Literal["<=", ">="] | None = None
    threshold: float | None = None
    hold_seconds: int | None = Field(default=None, gt=0)
    discovery_observed_count: int = Field(ge=0)
    discovery_usable_count: int = Field(ge=0)
    discovery_availability_fraction: float = Field(ge=0, le=1)
    discovery_mean_uplift: float | None = Field(default=None, ge=-10, le=10)
    discovery_uplift_lower_bound: float | None = Field(default=None, ge=-10, le=10)
    forward_observed_count: int = Field(default=0, ge=0)
    forward_usable_count: int = Field(default=0, ge=0)
    forward_availability_fraction: float = Field(default=0, ge=0, le=1)
    forward_season_count: int = Field(default=0, ge=0)
    forward_mean_uplift: float | None = Field(default=None, ge=-10, le=10)
    forward_uplift_lower_bound: float | None = Field(default=None, ge=-10, le=10)
    forward_uplift_upper_bound: float | None = Field(default=None, ge=-10, le=10)
    minimum_forward_samples: int = Field(default=60, gt=0)
    minimum_availability_fraction: float = Field(default=0.70, ge=0, le=1)
    last_evaluated_at: datetime | None = None
    influence_applied: Literal[False] = False


class OperationalIncident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    scope: str
    severity: str
    title: str
    detail: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrences: int = Field(ge=1)
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskLimits(BaseModel):
    mode: RiskMode
    order_size_sol: float
    min_net_edge_index: float
    max_danger: float
    min_confidence: float
    max_price_impact: float
    max_open_positions: int
    max_exposure_fraction: float
    max_drawdown_fraction: float
    stop_loss_fraction: float
    # Profit protection starts here. A healthy winner may continue until its
    # trailing guard, deteriorating evidence, or the absolute hold ceiling fires.
    take_profit_fraction: float
    trailing_stop_fraction: float
    minimum_hold_support: float
    migration_guard_progress: float
    # The former maximum is now the normal review point, not an unconditional exit.
    max_hold_seconds: int
    hard_max_hold_seconds: int


RISK_LIMITS: dict[RiskMode, RiskLimits] = {
    RiskMode.SAFE: RiskLimits(
        mode=RiskMode.SAFE,
        order_size_sol=0.01,
        min_net_edge_index=0.04,
        max_danger=0.25,
        min_confidence=0.72,
        max_price_impact=0.03,
        max_open_positions=2,
        max_exposure_fraction=0.05,
        max_drawdown_fraction=0.08,
        stop_loss_fraction=0.08,
        take_profit_fraction=0.15,
        trailing_stop_fraction=0.06,
        minimum_hold_support=0.62,
        migration_guard_progress=0.88,
        max_hold_seconds=300,
        hard_max_hold_seconds=900,
    ),
    RiskMode.BALANCED: RiskLimits(
        mode=RiskMode.BALANCED,
        order_size_sol=0.025,
        min_net_edge_index=0.025,
        max_danger=0.38,
        min_confidence=0.62,
        max_price_impact=0.06,
        max_open_positions=4,
        max_exposure_fraction=0.12,
        max_drawdown_fraction=0.15,
        stop_loss_fraction=0.12,
        take_profit_fraction=0.25,
        trailing_stop_fraction=0.10,
        minimum_hold_support=0.55,
        migration_guard_progress=0.92,
        max_hold_seconds=600,
        hard_max_hold_seconds=1_800,
    ),
    RiskMode.AGGRESSIVE: RiskLimits(
        mode=RiskMode.AGGRESSIVE,
        order_size_sol=0.05,
        min_net_edge_index=0.015,
        max_danger=0.50,
        min_confidence=0.55,
        max_price_impact=0.10,
        max_open_positions=6,
        max_exposure_fraction=0.20,
        max_drawdown_fraction=0.25,
        stop_loss_fraction=0.18,
        take_profit_fraction=0.40,
        trailing_stop_fraction=0.15,
        minimum_hold_support=0.48,
        migration_guard_progress=0.95,
        max_hold_seconds=1_200,
        hard_max_hold_seconds=3_600,
    ),
}


class PaperOrder(BaseModel):
    order_id: str
    decision_id: str | None = None
    mint: str
    symbol: str
    side: Side
    status: OrderStatus = OrderStatus.PENDING
    requested_sol_lamports: int = Field(default=0, ge=0)
    requested_token_units: int = Field(default=0, ge=0)
    # Account-currency cash reserved while a buy waits for its latency-aware fill.
    # Older persisted orders load with zero and are conservatively recalculated.
    reserved_account_minor: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    fill_after: datetime
    filled_at: datetime | None = None
    failure_reason: str | None = None
    # Added after V1 launch; None keeps older pending-order records loadable.
    risk_mode_at_entry: RiskMode | None = None


class FillReceipt(BaseModel):
    fill_id: str
    order_id: str
    mint: str
    symbol: str
    side: Side
    filled_at: datetime
    token_units: int = Field(ge=0)
    gross_sol_lamports: int = Field(ge=0)
    protocol_fee_lamports: int = Field(ge=0)
    network_fee_lamports: int = Field(ge=0)
    net_sol_lamports: int = Field(ge=0)
    price_impact_fraction: float = Field(ge=0, le=1)
    latency_ms: int = Field(ge=0)
    source_event_id: str
    venue: str
    assumptions: list[str] = Field(default_factory=list)
    account_currency: QuoteCurrency = QuoteCurrency.SOL
    account_decimals: int = Field(default=9, ge=0, le=18)
    account_gross_minor: int = Field(default=0, ge=0)
    account_protocol_fee_minor: int = Field(default=0, ge=0)
    account_network_fee_minor: int = Field(default=0, ge=0)
    account_net_minor: int = Field(default=0, ge=0)
    sol_usd_price: float | None = Field(default=None, gt=0)
    # Sell-side audit context. Defaults keep all existing immutable receipts readable.
    exit_assessment: ExitAssessment | None = None
    position_opened_at: datetime | None = None
    entry_risk_mode: RiskMode | None = None
    peak_account_minor: int = Field(default=0, ge=0)
    realized_return_fraction: float | None = Field(default=None, ge=-1, le=10)
    peak_return_fraction: float | None = Field(default=None, ge=-1, le=10)

    @model_validator(mode="after")
    def migrate_legacy_sol_account_values(self) -> FillReceipt:
        if self.account_currency != QuoteCurrency.SOL or self.account_net_minor != 0:
            return self
        self.account_gross_minor = self.gross_sol_lamports
        self.account_protocol_fee_minor = self.protocol_fee_lamports
        self.account_network_fee_minor = self.network_fee_lamports
        self.account_net_minor = self.net_sol_lamports
        return self


class Position(BaseModel):
    # The *_lamports names are retained for V1 database compatibility. In a USDC
    # portfolio they contain micro-USDC account units, as declared by PortfolioSnapshot.
    position_id: str
    mint: str
    symbol: str
    token_units: int = Field(ge=0)
    entry_cost_lamports: int = Field(ge=0)
    book_value_lamports: int = Field(ge=0)
    opened_at: datetime
    entry_fill_id: str
    # Persist the exact observed route so a restart can resume account verification even after
    # old create/trade events have been pruned from the bounded raw-event history.
    venue: str = "pump_curve"
    curve_address: str = ""
    pool_address: str = ""
    pool_base_token_account: str = ""
    pool_quote_token_account: str = ""
    quote_mint: str = "So11111111111111111111111111111111111111112"
    last_mark_lamports: int = Field(default=0, ge=0)
    unrealized_pnl_lamports: int = 0
    last_marked_at: datetime | None = None
    mark_age_seconds: float | None = Field(default=None, ge=0)
    mark_is_stale: bool = True
    # An indicative reserve calculation is not executable until the venue and quote route are
    # verified. Defaults intentionally make legacy records conservative after an upgrade.
    mark_is_executable: bool = False
    mark_blockers: list[str] = Field(default_factory=list)
    market_status: PositionMarketStatus = PositionMarketStatus.DORMANT
    # These fields are persisted inside the existing JSON record, so older databases
    # migrate through defaults without a destructive schema rewrite.
    risk_mode_at_entry: RiskMode | None = None
    peak_mark_lamports: int = Field(default=0, ge=0)
    peak_marked_at: datetime | None = None
    exit_assessment: ExitAssessment | None = None


class PortfolioSnapshot(BaseModel):
    # Monetary fields with legacy *_lamports names use quote_currency/quote_decimals.
    # They are lamports for SOL and micro-USDC for USDC.
    initialized: bool
    quote_currency: QuoteCurrency
    quote_decimals: int = Field(ge=0, le=18)
    cash_lamports: int
    reserved_cash_lamports: int = Field(default=0, ge=0)
    available_cash_lamports: int = Field(default=0, ge=0)
    invested_value_lamports: int = Field(default=0, ge=0)
    last_known_invested_value_lamports: int = Field(default=0, ge=0)
    stale_invested_value_lamports: int = Field(default=0, ge=0)
    stale_position_count: int = Field(default=0, ge=0)
    route_blocked_invested_value_lamports: int = Field(default=0, ge=0)
    route_blocked_position_count: int = Field(default=0, ge=0)
    excluded_invested_value_lamports: int = Field(default=0, ge=0)
    excluded_position_count: int = Field(default=0, ge=0)
    starting_lamports: int
    equity_lamports: int
    last_known_equity_lamports: int = Field(default=0, ge=0)
    realized_pnl_lamports: int
    unrealized_pnl_lamports: int
    drawdown_fraction: float
    risk_halted: bool = False
    risk_halt_reason: str | None = None
    positions: list[Position]
    pending_orders: list[PaperOrder]
