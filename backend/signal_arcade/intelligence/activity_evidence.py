"""Immutable, bounded enrollment metadata. Never a model input or trading gate."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
)

from ..models import Decision, IntegrityAssessment, LearningEvidenceEpisode, LearningObservation
from .activity import ACTIVITY_UNITS

MAX_ACTIVITY_EVIDENCE_BYTES = 4096
ACTIVITY_EVIDENCE_VERSION: Final = "activity-evidence-v1"
Parent = LearningObservation | LearningEvidenceEpisode
# Preserve the raw operands, not the learner's clamped feature vector. This is a fixed
# projection, not a complete snapshot and not independent manipulation ground truth.
CONTEXT_METRICS = (
    "buy_ratio_5m",
    "trade_count_1m",
    "trade_count_5m",
    "unique_wallets_5m",
    "known_wallet_trade_coverage",
    "signed_trade_coverage",
    "trade_window_span_seconds",
    "trade_buffer_saturated",
    "integrity_window_complete",
    "age_seconds",
    "wallet_volume_hhi",
    "single_trade_wallet_ratio",
    "round_trip_wallet_ratio",
    "round_trip_volume_ratio",
    "net_quote_flow_ratio",
    "side_alternation_ratio",
    "quantized_amount_repeat_ratio",
    "slot_concentration_hhi",
    "price_direction_consistency",
    "multi_trade_signature_ratio",
    "microtrade_count_ratio",
    "meaningful_volume_ratio",
    "meaningful_wallet_ratio",
    "median_trade_quote_sol",
    "price_path_efficiency",
    "rapid_price_reversal_ratio",
    "trade_density_5m",
)
METRICS = (*ACTIVITY_UNITS, *CONTEXT_METRICS)
COUNT_METRICS = {name for name, unit in ACTIVITY_UNITS.items() if unit == "count"} | {
    "unique_wallets_5m",
    "trade_count_1m",
    "trade_count_5m",
}
BOOL_METRICS = {"trade_buffer_saturated", "integrity_window_complete"}
UNBOUNDED_METRICS = {"age_seconds", "trade_window_span_seconds", "median_trade_quote_sol"}
# value, quality, timestamp index, missing reason. Deduplicated clocks keep the complete
# allowlist under a hard byte cap without rounding measurements or dropping missing fields.
Cell = tuple[StrictFloat | StrictInt | StrictBool | None, StrictFloat, StrictInt | None, str | None]


class ActivityContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    baseline: str
    features: str
    configuration: str | None
    season: str | None
    profile: str | None
    risk: str
    venue: str
    quote: str | None


class ActivityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    version: Literal["activity-evidence-v1"] = ACTIVITY_EVIDENCE_VERSION
    parent_kind: Literal["discovery", "policy"]
    parent_id: str
    decision_id: str | None
    mint: str
    decision_at: datetime
    context: ActivityContext
    cutoff_lamports: Literal[10_000_000] = 10_000_000
    windows_seconds: tuple[Literal[60], Literal[300]] = (60, 300)
    status: Literal["complete", "partial", "unavailable"]
    reason: str | None = None
    clocks: list[datetime] = Field(default_factory=list, max_length=len(METRICS))
    metrics: dict[str, Cell] = Field(default_factory=dict)
    integrity: IntegrityAssessment | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.decision_at.utcoffset() is None:
            raise ValueError("naive decision timestamp")
        if any(t.utcoffset() is None or t > self.decision_at for t in self.clocks):
            raise ValueError("invalid measurement timestamp")
        if self.status == "unavailable":
            if not self.reason or self.metrics or self.clocks or self.integrity is not None:
                raise ValueError("unavailable evidence must not imply a partial measurement")
            return self
        if self.reason is not None or set(self.metrics) != set(METRICS):
            raise ValueError("incomplete metric projection")
        for name, (value, quality, clock, reason) in self.metrics.items():
            if not math.isfinite(quality) or not 0 <= quality <= 1:
                raise ValueError("invalid quality")
            if clock is not None and (isinstance(clock, bool) or not 0 <= clock < len(self.clocks)):
                raise ValueError("invalid clock index")
            if value is None:
                if not reason:
                    raise ValueError("unknown needs a reason")
                continue
            if clock is None or (reason is not None and name in ACTIVITY_UNITS):
                raise ValueError("value without usable provenance")
            if name in BOOL_METRICS:
                if not isinstance(value, bool):
                    raise ValueError("boolean evidence required")
            elif isinstance(value, bool) or not math.isfinite(value):
                raise ValueError("invalid numeric evidence")
            elif name in COUNT_METRICS:
                if value < 0 or int(value) != value:
                    raise ValueError("invalid count")
            elif name in UNBOUNDED_METRICS:
                if value < 0:
                    raise ValueError("negative measurement")
            elif not (-1 if name == "signed_net_quote_flow_ratio_5m" else 0) <= value <= 1:
                raise ValueError("invalid fraction")
        activity_clocks = {self.metrics[n][2] for n in ACTIVITY_UNITS} - {None}
        if len(activity_clocks) > 1:
            raise ValueError("activity metrics must describe one cached window")
        amount_coverage = self.metrics["trade_amount_coverage_5m"][0]
        for name in ACTIVITY_UNITS:
            value, quality, _, _ = self.metrics[name]
            if (
                name != "trade_amount_coverage_5m"
                and value is not None
                and (amount_coverage != 1 or quality != 1)
            ):
                raise ValueError("partial activity cannot masquerade as a complete measurement")
        for smaller, larger in (
            ("trade_count_1m", "trade_count_5m"),
            ("unique_wallets_5m", "trade_count_5m"),
            ("meaningful_trade_count_1m", "meaningful_trade_count_5m"),
            ("meaningful_trade_count_1m", "trade_count_1m"),
            ("meaningful_trade_count_5m", "trade_count_5m"),
            ("meaningful_trade_wallet_count_5m", "meaningful_trade_count_5m"),
            ("meaningful_trade_wallet_count_5m", "unique_wallets_5m"),
            ("net_buy_wallet_count_5m", "unique_wallets_5m"),
        ):
            a, b = self.metrics[smaller][0], self.metrics[larger][0]
            if a is not None and b is not None and a > b:
                raise ValueError("contradictory counts")
        buy, flow = (
            self.metrics[n][0]
            for n in ("buy_quote_volume_ratio_5m", "signed_net_quote_flow_ratio_5m")
        )
        if (
            buy is not None
            and flow is not None
            and not math.isclose(2 * buy - 1, flow, abs_tol=1e-12)
        ):
            raise ValueError("contradictory flow")
        complete = self.integrity is not None and all(
            c[0] is not None and c[3] is None for c in self.metrics.values()
        )
        if (self.status == "complete") != complete:
            raise ValueError("incorrect completeness")
        return self

    def matches(self, parent: Parent) -> bool:
        kind, parent_id = parent_identity(parent)
        if isinstance(parent, LearningEvidenceEpisode) and (
            self.context.venue != parent.venue
            or self.context.quote != parent.quote_mint
            or self.decision_at != parent.entry_at
        ):
            return False
        return (
            self.parent_kind,
            self.parent_id,
            self.decision_id,
            self.mint,
            self.decision_at,
        ) == (kind, parent_id, parent.decision_id, parent.mint, parent.created_at) and (
            self.context.baseline,
            self.context.features,
            self.context.configuration,
            self.context.season,
            self.context.profile,
            self.context.risk,
        ) == (
            parent.baseline_version,
            parent.feature_schema_version,
            parent.configuration_fingerprint,
            parent.season_id,
            parent.season_profile_fingerprint,
            parent.risk_mode.value,
        )


def parent_identity(parent: Parent) -> tuple[Literal["discovery", "policy"], str]:
    if isinstance(parent, LearningObservation):
        return "discovery", parent.observation_id
    if parent.lane.value != "policy":
        raise ValueError("activity evidence belongs to Discovery or Policy")
    return "policy", parent.episode_id


def capture_activity(parent: Parent, decision: Decision, quote: str | None) -> ActivityEvidence:
    """Only called at enrollment. All inputs already exist; no scans or provider work."""
    kind, parent_id = parent_identity(parent)
    base = ActivityEvidence(
        parent_kind=kind,
        parent_id=parent_id,
        decision_id=parent.decision_id,
        mint=parent.mint,
        decision_at=parent.created_at,
        status="unavailable",
        reason="invalid_capture",
        context=ActivityContext(
            baseline=parent.baseline_version,
            features=parent.feature_schema_version,
            configuration=parent.configuration_fingerprint,
            season=parent.season_id,
            profile=parent.season_profile_fingerprint,
            risk=parent.risk_mode.value,
            venue=decision.feature_snapshot.venue,
            quote=quote,
        ),
    )
    # The parent is authoritative. Optional source failure may not remove a core lesson.
    try:
        if (parent.decision_id, parent.mint, parent.created_at) != (
            decision.decision_id,
            decision.mint,
            decision.created_at,
        ) or decision.feature_snapshot.mint != parent.mint:
            raise ValueError("identity mismatch")
        if (
            parent.baseline_version != decision.model_version.split("+", maxsplit=1)[0]
            or parent.risk_mode != decision.risk_mode
            or parent.configuration_fingerprint != decision.configuration_fingerprint
            or parent.season_id != decision.season_id
            or parent.season_profile_fingerprint != decision.season_profile_fingerprint
        ):
            raise ValueError("decision context mismatch")
        if isinstance(parent, LearningEvidenceEpisode) and (
            parent.venue != decision.feature_snapshot.venue
            or parent.quote_mint != quote
            or parent.entry_at != decision.created_at
        ):
            raise ValueError("route context mismatch")
        clocks: list[datetime] = []
        metrics: dict[str, Cell] = {}
        for name in METRICS:
            item = decision.feature_snapshot.values.get(name)
            if item is None:
                metrics[name] = (None, 0.0, None, "not_recorded")
                continue
            if item.as_of not in clocks:
                clocks.append(item.as_of)
            if isinstance(item.value, str):
                raise ValueError("numeric activity cannot be a string")
            # Preserve unknowns explicitly, never manufacture a numeric zero.
            metrics[name] = (
                item.value,
                item.quality,
                clocks.index(item.as_of),
                item.missing_reason or ("unavailable" if item.value is None else None),
            )
        complete = decision.integrity_assessment is not None and all(
            c[0] is not None and c[3] is None for c in metrics.values()
        )
        result = ActivityEvidence.model_validate(
            {
                **base.model_dump(),
                "status": "complete" if complete else "partial",
                "reason": None,
                "clocks": clocks,
                "metrics": metrics,
                "integrity": (
                    decision.integrity_assessment.model_dump()
                    if decision.integrity_assessment is not None
                    else None
                ),
            }
        )
        if len(result.model_dump_json().encode()) <= MAX_ACTIVITY_EVIDENCE_BYTES:
            return result
        reason = "payload_too_large"
    except (ValueError, TypeError, OverflowError):
        reason = "invalid_capture"
    return base.model_copy(update={"reason": reason})


def read_activity(payload: str, parent: Parent) -> ActivityEvidence:
    if len(payload.encode()) > MAX_ACTIVITY_EVIDENCE_BYTES:
        raise ValueError("oversized activity evidence")
    try:
        record = ActivityEvidence.model_validate_json(payload)
    except OverflowError as exc:
        raise ValueError("invalid numeric activity evidence") from exc
    if not record.matches(parent):
        raise ValueError("activity parent/context mismatch")
    return record
