from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .database import Database
from .intelligence.learning import LEARNING_HORIZONS_SECONDS, PRIMARY_HORIZON_SECONDS
from .models import (
    RISK_LIMITS,
    CoachExperimentKind,
    CoachExperimentState,
    CoachHypothesis,
    CoachReview,
    DecisionAction,
    LearningObservation,
    RiskMode,
)
from .providers.http import HttpProviders

logger = logging.getLogger(__name__)

COACH_PROMPT_VERSION = "coach-shadow-v2"
COACH_SCHEMA_VERSION = "coach-shadow-schema-v2"
COACH_REVIEW_INTERVAL_OUTCOMES = 25
COACH_FIRST_REVIEW_OUTCOMES = 80
COACH_MINIMUM_DISCOVERY_SAMPLES = 20
COACH_MINIMUM_FORWARD_SAMPLES = 60
COACH_REJECTION_SAMPLES = 120
COACH_MINIMUM_AVAILABILITY = 0.70
COACH_MINIMUM_FORWARD_SEASONS = 2
COACH_MINIMUM_UPLIFT = 0.01
COACH_MONITOR_SECONDS = 30
COACH_RETRY_SECONDS = 300
COACH_INFERENCE_TIMEOUT_SECONDS = 75
COACH_OBSERVATION_WINDOW = 1_000
COACH_MAX_CANDIDATES = 6
COACH_Z_SCORE = 1.96

_FEATURE_LABELS = {
    "buy_ratio": "low buy participation",
    "concentration": "high wallet concentration",
    "danger": "higher measured danger",
    "drawdown": "deeper recent drawdown",
    "execution": "weaker execution quality",
    "confidence": "lower evidence confidence",
    "momentum": "weak short-term momentum",
    "single_trade_wallet_ratio": "one-trade wallets dominate participation",
    "round_trip_wallet_ratio": "many wallets rapidly buy and sell",
    "round_trip_volume_ratio": "round-trip wallets dominate volume",
    "net_quote_flow_ratio": "gross volume produces little net flow",
    "side_alternation_ratio": "buys and sells alternate unusually often",
    "quantized_amount_repeat_ratio": "trade sizes cluster unusually tightly",
    "slot_concentration_hhi": "activity concentrates into few slots",
    "price_direction_consistency": "the price path is unusually one-way",
}

_ENTRY_RULES: tuple[tuple[str, str, float], ...] = (
    ("momentum", "<=", -0.05),
    ("momentum", "<=", 0.00),
    ("buy_ratio", "<=", 0.50),
    ("buy_ratio", "<=", 0.55),
    ("concentration", ">=", 0.35),
    ("concentration", ">=", 0.50),
    ("drawdown", ">=", 0.18),
    ("drawdown", ">=", 0.30),
    ("danger", ">=", 0.20),
    ("danger", ">=", 0.30),
    ("execution", "<=", 0.85),
    ("confidence", "<=", 0.72),
    ("single_trade_wallet_ratio", ">=", 0.90),
    ("round_trip_wallet_ratio", ">=", 0.35),
    ("round_trip_volume_ratio", ">=", 0.50),
    ("net_quote_flow_ratio", "<=", 0.20),
    ("side_alternation_ratio", ">=", 0.75),
    ("quantized_amount_repeat_ratio", ">=", 0.40),
    ("slot_concentration_hhi", ">=", 0.30),
    ("price_direction_consistency", ">=", 0.90),
)


class _CoachSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(max_length=80)
    summary: str = Field(max_length=240)


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    signature: str
    kind: CoachExperimentKind
    title: str
    feature_name: str | None
    operator: str | None
    threshold: float | None
    hold_seconds: int | None
    observed_count: int
    usable_count: int
    availability_fraction: float
    mean_uplift: float
    uplift_lower_bound: float
    uplift_upper_bound: float

    def prompt_view(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind.value,
            "experiment": self.title,
            "observed": self.observed_count,
            "usable": self.usable_count,
            "availability": round(self.availability_fraction, 4),
            "historical_mean_uplift": round(self.mean_uplift, 6),
            "historical_lower_bound": round(self.uplift_lower_bound, 6),
            "historical_upper_bound": round(self.uplift_upper_bound, 6),
        }


class AiCoach:
    """Slow, zero-influence coach whose proposals need new forward paper evidence."""

    def __init__(
        self,
        database: Database,
        http: HttpProviders,
        *,
        enabled: Callable[[], bool],
        context: Callable[[], tuple[RiskMode, str]],
        outcomes_seen: Callable[[], int],
        model_provenance: Callable[[], tuple[str, str]],
        can_run: Callable[[], tuple[bool, str | None]],
    ) -> None:
        self.database = database
        self.http = http
        self.enabled = enabled
        self.context = context
        self.outcomes_seen = outcomes_seen
        self.model_provenance = model_provenance
        self.can_run = can_run
        self.task: asyncio.Task[None] | None = None
        self.busy = False
        self.last_error: str | None = None
        self.paused_reason: str | None = None
        self.last_attempt_at: datetime | None = None
        self.next_attempt_at: datetime | None = None
        self.reviews = database.list_coach_reviews(25)
        self.hypotheses = database.list_coach_hypotheses(100)

    async def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._monitor_loop(), name="ai-coach-shadow")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        self.busy = False

    async def _monitor_loop(self) -> None:
        await asyncio.sleep(15)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Optional reflection can fail without changing or delaying a paper action.
                logger.warning("AI Coach Shadow recovered from %s", type(exc).__name__)
                self.last_error = "coach_review_failed_safely"
                self.next_attempt_at = datetime.now(UTC) + timedelta(seconds=COACH_RETRY_SECONDS)
            await asyncio.sleep(COACH_MONITOR_SECONDS)

    async def tick(self) -> None:
        now = datetime.now(UTC)
        if not self.enabled():
            self.paused_reason = "ai_shadow_off"
            return
        await asyncio.to_thread(self._refresh_hypotheses, now)
        mode, fingerprint = self.context()
        active = self._active_hypothesis(mode, fingerprint)
        if active is not None:
            self.paused_reason = "forward_test_in_progress"
            return
        seen = max(0, self.outcomes_seen())
        last_seen = max(
            (
                review.outcomes_seen
                for review in self.reviews
                if review.valid
                and review.risk_mode == mode
                and review.configuration_fingerprint == fingerprint
            ),
            default=0,
        )
        required = (
            COACH_FIRST_REVIEW_OUTCOMES
            if last_seen == 0
            else last_seen + COACH_REVIEW_INTERVAL_OUTCOMES
        )
        if seen < required:
            self.paused_reason = "waiting_for_outcomes"
            return
        allowed, reason = self.can_run()
        if not allowed:
            self.paused_reason = reason or "protecting_market_work"
            return
        if self.next_attempt_at is not None and now < self.next_attempt_at:
            self.paused_reason = "retry_backoff"
            return
        if self.http.ollama_generation_busy:
            self.paused_reason = "ollama_busy"
            return

        self.busy = True
        self.paused_reason = None
        self.last_attempt_at = now
        try:
            observations = await asyncio.to_thread(
                self.database.recent_learning_observations,
                COACH_OBSERVATION_WINDOW,
            )
            excluded = {
                item.signature
                for item in self.hypotheses
                if item.risk_mode == mode and item.configuration_fingerprint == fingerprint
            }
            candidates = _build_candidates(observations, mode, fingerprint, excluded)
            model_name, model_digest = self.model_provenance()
            if not candidates:
                review = _review_without_candidate(
                    now=now,
                    outcomes_seen=seen,
                    mode=mode,
                    fingerprint=fingerprint,
                    model_name=model_name,
                    model_digest=model_digest,
                )
                await asyncio.to_thread(self._save_review, review)
                self.last_error = None
                return

            prompt_payload = {
                "role": "post-trade coach",
                "rule": (
                    "Historical screening may reject an idea but cannot qualify it. Select one "
                    "bounded candidate for a new forward-only Shadow test, or none when the "
                    "evidence is not conservative enough. Never invent a candidate."
                ),
                "candidates": [item.prompt_view() for item in candidates],
            }
            serialized = json.dumps(prompt_payload, separators=(",", ":"), sort_keys=True)
            schema = _selection_schema([item.candidate_id for item in candidates])
            response = await self.http.ollama_structured(
                prompt=(
                    "Choose one candidate_id from the supplied JSON or 'none'. Give one short "
                    "plain summary explaining the evidence tradeoff. Output only the schema. JSON:"
                    + serialized
                ),
                schema=schema,
                # Unlike the fast critic, Coach Shadow never sits in a decision path. Give a
                # CPU-only mini PC enough room for one cold model load while retaining a hard
                # bound and the existing five-minute failure backoff.
                timeout_seconds=COACH_INFERENCE_TIMEOUT_SECONDS,
            )
            current_mode, current_fingerprint = self.context()
            if current_mode != mode or current_fingerprint != fingerprint:
                self.last_error = "context_changed_during_review"
                self.next_attempt_at = now + timedelta(seconds=COACH_RETRY_SECONDS)
                return
            if response is None:
                review = _failed_review(
                    now=now,
                    outcomes_seen=seen,
                    mode=mode,
                    fingerprint=fingerprint,
                    model_name=model_name,
                    model_digest=model_digest,
                    input_sha256=hashlib.sha256(serialized.encode()).hexdigest(),
                    candidate_count=len(candidates),
                    reason="ollama_unavailable_or_timed_out",
                )
                await asyncio.to_thread(self._save_review, review)
                self.last_error = review.failure_reason
                self.next_attempt_at = now + timedelta(seconds=COACH_RETRY_SECONDS)
                return
            raw, latency_ms = response
            try:
                selection = _CoachSelection.model_validate_json(raw)
            except ValidationError:
                selection = None
            candidate = next(
                (
                    item
                    for item in candidates
                    if selection is not None and item.candidate_id == selection.candidate_id
                ),
                None,
            )
            valid = bool(selection is not None and (selection.candidate_id == "none" or candidate))
            review = CoachReview(
                review_id="coach-review-" + uuid.uuid4().hex,
                created_at=now,
                cutoff_at=now,
                outcomes_seen=seen,
                risk_mode=mode,
                configuration_fingerprint=fingerprint,
                model_name=model_name,
                model_digest=model_digest,
                prompt_version=COACH_PROMPT_VERSION,
                schema_version=COACH_SCHEMA_VERSION,
                input_sha256=hashlib.sha256(serialized.encode()).hexdigest(),
                candidate_count=len(candidates),
                latency_ms=latency_ms,
                valid=valid,
                selected_candidate_id=(selection.candidate_id if valid and selection else None),
                summary=(
                    _clean_text(selection.summary, 240)
                    if valid and selection
                    else "The local coach response did not match the bounded experiment schema."
                ),
                failure_reason=None if valid else "invalid_structured_response",
            )
            await asyncio.to_thread(self._save_review, review)
            if not valid:
                self.last_error = review.failure_reason
                self.next_attempt_at = now + timedelta(seconds=COACH_RETRY_SECONDS)
                return
            self.last_error = None
            self.next_attempt_at = None
            if candidate is not None:
                hypothesis = _hypothesis_from_candidate(
                    review,
                    candidate,
                    selection.summary if selection is not None else "",
                )
                await asyncio.to_thread(self._save_hypothesis, hypothesis)
        finally:
            self.busy = False

    def _save_review(self, review: CoachReview) -> None:
        self.database.save_coach_review(review)
        retained = [item for item in self.reviews if item.review_id != review.review_id]
        self.reviews = [review, *retained][:25]
        self.database.prune_coach_history()

    def _save_hypothesis(self, hypothesis: CoachHypothesis) -> None:
        self.database.save_coach_hypothesis(hypothesis)
        self.hypotheses = [
            hypothesis,
            *[item for item in self.hypotheses if item.hypothesis_id != hypothesis.hypothesis_id],
        ][:100]

    def _refresh_hypotheses(self, now: datetime) -> None:
        if not self.hypotheses:
            return
        observations = self.database.recent_learning_observations(COACH_OBSERVATION_WINDOW)
        refreshed: list[CoachHypothesis] = []
        for hypothesis in self.hypotheses:
            updated = _evaluate_hypothesis(hypothesis, observations, now)
            if updated != hypothesis:
                self.database.save_coach_hypothesis(updated)
            refreshed.append(updated)
        self.hypotheses = refreshed

    def _active_hypothesis(self, mode: RiskMode, fingerprint: str) -> CoachHypothesis | None:
        return next(
            (
                item
                for item in self.hypotheses
                if item.risk_mode == mode
                and item.configuration_fingerprint == fingerprint
                and item.state
                in {
                    CoachExperimentState.TESTING,
                    CoachExperimentState.PROMISING,
                }
            ),
            None,
        )

    def status(self) -> dict[str, Any]:
        mode, fingerprint = self.context()
        seen = max(0, self.outcomes_seen())
        active = self._active_hypothesis(mode, fingerprint)
        last_valid_seen = max(
            (
                review.outcomes_seen
                for review in self.reviews
                if review.valid
                and review.risk_mode == mode
                and review.configuration_fingerprint == fingerprint
            ),
            default=0,
        )
        next_at = (
            COACH_FIRST_REVIEW_OUTCOMES
            if last_valid_seen == 0
            else last_valid_seen + COACH_REVIEW_INTERVAL_OUTCOMES
        )
        state = (
            "off"
            if not self.enabled()
            else "reviewing"
            if self.busy
            else active.state.value
            if active is not None
            else "waiting"
        )
        qualification_gates = _coach_qualification_gates(active)
        recent_hypotheses = []
        for item in self.hypotheses[:6]:
            view = item.model_dump(mode="json")
            view["context_active"] = bool(
                item.risk_mode == mode and item.configuration_fingerprint == fingerprint
            )
            recent_hypotheses.append(view)
        return {
            "mode": "shadow" if self.enabled() else "off",
            "state": state,
            "influence": "none",
            "worker_running": self.task is not None and not self.task.done(),
            "busy": self.busy,
            "paused_reason": self.paused_reason,
            "last_error": self.last_error,
            "last_attempt_at": self.last_attempt_at,
            "review_interval_outcomes": COACH_REVIEW_INTERVAL_OUTCOMES,
            "outcomes_seen": seen,
            "outcomes_until_review": max(0, next_at - seen) if active is None else 0,
            "minimum_forward_samples": COACH_MINIMUM_FORWARD_SAMPLES,
            "minimum_forward_seasons": COACH_MINIMUM_FORWARD_SEASONS,
            "qualification_gates": qualification_gates,
            "qualification_passed": sum(gate["state"] == "passed" for gate in qualification_gates),
            "qualification_total": len(qualification_gates),
            "recent_hypotheses": recent_hypotheses,
            "recent_reviews": [item.model_dump(mode="json") for item in self.reviews[:3]],
            "guardrails": [
                "Coach work is asynchronous and cannot delay an entry, exit, or dashboard read",
                "The local model selects only from deterministic allowlisted experiments",
                "Historical evidence can reject an idea but only newer outcomes can support it",
                "Coach Shadow never changes an action, position size, risk mode, or safety gate",
                "Unavailable exits remain unknown and prevent qualification when coverage is low",
                "Experiments are isolated by risk mode and fee/provider configuration",
            ],
        }


def _coach_qualification_gates(
    hypothesis: CoachHypothesis | None,
) -> list[dict[str, Any]]:
    """Describe Shadow experiment proof; it never implies that influence exists."""

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

    exists = hypothesis is not None
    usable = hypothesis.forward_usable_count if hypothesis else None
    availability = hypothesis.forward_availability_fraction if hypothesis else None
    seasons = hypothesis.forward_season_count if hypothesis else None
    uplift_floor = hypothesis.forward_uplift_lower_bound if hypothesis else None
    return [
        gate(
            "experiment_selected",
            "Bounded experiment selected",
            exists,
            True,
            "=",
            exists,
            "boolean",
            "The local model may select only from deterministic allowlisted experiments.",
        ),
        gate(
            "forward_outcomes",
            "New forward outcomes",
            usable,
            COACH_MINIMUM_FORWARD_SAMPLES,
            ">=",
            usable is not None and usable >= COACH_MINIMUM_FORWARD_SAMPLES,
            "count",
            "Only outcomes created after the idea was proposed may support it.",
        ),
        gate(
            "outcome_coverage",
            "Forward outcome coverage",
            availability,
            COACH_MINIMUM_AVAILABILITY,
            ">=",
            availability is not None and availability >= COACH_MINIMUM_AVAILABILITY,
            "fraction",
            "Unavailable executable exits prevent an experiment from looking safer than it is.",
        ),
        gate(
            "independent_seasons",
            "Independent seasons",
            seasons,
            COACH_MINIMUM_FORWARD_SEASONS,
            ">=",
            seasons is not None and seasons >= COACH_MINIMUM_FORWARD_SEASONS,
            "count",
            "The idea must survive more than one paper season.",
        ),
        gate(
            "uplift_floor",
            "Conservative forward value",
            uplift_floor,
            COACH_MINIMUM_UPLIFT,
            ">",
            uplift_floor is not None and uplift_floor > COACH_MINIMUM_UPLIFT,
            "fraction",
            "The confidence-adjusted forward improvement must exceed one percentage point.",
        ),
        gate(
            "promising",
            "Shadow proof complete",
            hypothesis.state == CoachExperimentState.PROMISING if hypothesis else None,
            True,
            "=",
            hypothesis is not None and hypothesis.state == CoachExperimentState.PROMISING,
            "boolean",
            "Promising is a research milestone only; current Coach influence remains zero.",
        ),
    ]


def _build_candidates(
    observations: Sequence[LearningObservation],
    mode: RiskMode,
    fingerprint: str,
    excluded_signatures: set[str],
) -> list[_Candidate]:
    context_rows = [
        item
        for item in observations
        if item.risk_mode == mode and item.configuration_fingerprint == fingerprint
    ]
    actionable_entries = [
        item
        for item in context_rows
        if item.baseline_action == DecisionAction.ENTER and item.baseline_actionable
    ]
    candidates: list[_Candidate] = []
    for feature, operator, threshold in _ENTRY_RULES:
        signature = _signature(
            CoachExperimentKind.ENTRY_VETO,
            mode,
            fingerprint,
            feature,
            operator,
            threshold,
            None,
        )
        if signature in excluded_signatures:
            continue
        matched = [
            item
            for item in context_rows
            if item.baseline_action == DecisionAction.ENTER
            and item.baseline_actionable
            and _condition_matches(item, feature, operator, threshold)
        ]
        stats = _entry_stats(matched)
        if (
            stats is None
            or stats[1] < COACH_MINIMUM_DISCOVERY_SAMPLES
            or stats[2] < COACH_MINIMUM_AVAILABILITY
            or stats[3] <= 0
        ):
            continue
        observed, usable, availability, mean, lower, upper = stats
        label = _FEATURE_LABELS[feature]
        candidates.append(
            _Candidate(
                candidate_id="candidate-" + signature[:16],
                signature=signature,
                kind=CoachExperimentKind.ENTRY_VETO,
                title=f"Test preserving cash when {label}",
                feature_name=feature,
                operator=operator,
                threshold=threshold,
                hold_seconds=None,
                observed_count=observed,
                usable_count=usable,
                availability_fraction=availability,
                mean_uplift=mean,
                uplift_lower_bound=lower,
                uplift_upper_bound=upper,
            )
        )

    baseline_hold = RISK_LIMITS[mode].max_hold_seconds
    for horizon in LEARNING_HORIZONS_SECONDS:
        if horizon >= baseline_hold:
            continue
        signature = _signature(
            CoachExperimentKind.EARLIER_REVIEW,
            mode,
            fingerprint,
            None,
            None,
            None,
            horizon,
        )
        if signature in excluded_signatures:
            continue
        stats = _hold_stats(actionable_entries, horizon, baseline_hold)
        if (
            stats is None
            or stats[1] < COACH_MINIMUM_DISCOVERY_SAMPLES
            or stats[2] < COACH_MINIMUM_AVAILABILITY
            or stats[3] <= 0
        ):
            continue
        observed, usable, availability, mean, lower, upper = stats
        candidates.append(
            _Candidate(
                candidate_id="candidate-" + signature[:16],
                signature=signature,
                kind=CoachExperimentKind.EARLIER_REVIEW,
                title=f"Test reviewing normal holds at {horizon // 60}m",
                feature_name=None,
                operator=None,
                threshold=None,
                hold_seconds=horizon,
                observed_count=observed,
                usable_count=usable,
                availability_fraction=availability,
                mean_uplift=mean,
                uplift_lower_bound=lower,
                uplift_upper_bound=upper,
            )
        )
    candidates.sort(
        key=lambda item: (item.uplift_lower_bound, item.mean_uplift, item.usable_count),
        reverse=True,
    )
    return candidates[:COACH_MAX_CANDIDATES]


def _entry_stats(
    observations: Sequence[LearningObservation],
) -> tuple[int, int, float, float, float, float] | None:
    checkpoints = [
        item.checkpoints[str(PRIMARY_HORIZON_SECONDS)]
        for item in observations
        if str(PRIMARY_HORIZON_SECONDS) in item.checkpoints
    ]
    values = [-item.net_return for item in checkpoints if item.net_return is not None]
    return _stats(len(checkpoints), values)


def _hold_stats(
    observations: Sequence[LearningObservation],
    selected: int,
    baseline: int,
) -> tuple[int, int, float, float, float, float] | None:
    observed = [
        item
        for item in observations
        if str(selected) in item.checkpoints and str(baseline) in item.checkpoints
    ]
    values = []
    for item in observed:
        selected_return = item.checkpoints[str(selected)].net_return
        baseline_return = item.checkpoints[str(baseline)].net_return
        if selected_return is not None and baseline_return is not None:
            values.append(selected_return - baseline_return)
    return _stats(len(observed), values)


def _stats(
    observed: int,
    values: Sequence[float],
) -> tuple[int, int, float, float, float, float] | None:
    if observed <= 0 or not values:
        return None
    mean, lower, upper = _mean_bounds(values)
    return observed, len(values), len(values) / observed, mean, lower, upper


def _mean_bounds(values: Sequence[float]) -> tuple[float, float, float]:
    mean = fmean(values)
    if len(values) < 2:
        return mean, max(-10.0, mean - 1.0), min(10.0, mean + 1.0)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = COACH_Z_SCORE * math.sqrt(variance / len(values))
    return mean, max(-10.0, mean - margin), min(10.0, mean + margin)


def _evaluate_hypothesis(
    hypothesis: CoachHypothesis,
    observations: Sequence[LearningObservation],
    now: datetime,
) -> CoachHypothesis:
    if hypothesis.state in {
        CoachExperimentState.INCONCLUSIVE,
        CoachExperimentState.NOT_SUPPORTED,
    }:
        # These are recorded terminal outcomes. The signature remains excluded from future
        # proposals, and later ambient observations cannot silently revive an old experiment
        # alongside the context's newer active test.
        return hypothesis
    rows = [
        item
        for item in observations
        if item.created_at > hypothesis.cutoff_at
        and item.risk_mode == hypothesis.risk_mode
        and item.configuration_fingerprint == hypothesis.configuration_fingerprint
    ]
    if hypothesis.kind == CoachExperimentKind.ENTRY_VETO:
        rows = [
            item
            for item in rows
            if item.baseline_action == DecisionAction.ENTER
            and item.baseline_actionable
            and hypothesis.feature_name is not None
            and hypothesis.operator is not None
            and hypothesis.threshold is not None
            and _condition_matches(
                item,
                hypothesis.feature_name,
                hypothesis.operator,
                hypothesis.threshold,
            )
        ]
        stats = _entry_stats(rows)
        observed_rows = [item for item in rows if str(PRIMARY_HORIZON_SECONDS) in item.checkpoints]
    else:
        rows = [
            item
            for item in rows
            if item.baseline_action == DecisionAction.ENTER and item.baseline_actionable
        ]
        baseline = RISK_LIMITS[hypothesis.risk_mode].max_hold_seconds
        selected = hypothesis.hold_seconds or baseline
        stats = _hold_stats(rows, selected, baseline)
        observed_rows = [
            item
            for item in rows
            if str(selected) in item.checkpoints and str(baseline) in item.checkpoints
        ]
    if stats is None:
        observed = len(observed_rows)
        usable = 0
        availability = 0.0
        mean = lower = upper = None
    else:
        observed, usable, availability, mean, lower, upper = stats
    seasons = {item.season_id for item in observed_rows if item.season_id}
    state = CoachExperimentState.TESTING
    if (
        observed >= hypothesis.minimum_forward_samples
        and availability < hypothesis.minimum_availability_fraction
    ):
        state = CoachExperimentState.INCONCLUSIVE
    elif (
        usable >= hypothesis.minimum_forward_samples
        and availability >= hypothesis.minimum_availability_fraction
        and len(seasons) >= COACH_MINIMUM_FORWARD_SEASONS
        and lower is not None
        and lower > COACH_MINIMUM_UPLIFT
    ):
        state = CoachExperimentState.PROMISING
    elif usable >= COACH_REJECTION_SAMPLES and upper is not None and upper <= 0:
        state = CoachExperimentState.NOT_SUPPORTED
    evidence = {
        "state": state,
        "forward_observed_count": observed,
        "forward_usable_count": usable,
        "forward_availability_fraction": availability,
        "forward_season_count": len(seasons),
        "forward_mean_uplift": mean,
        "forward_uplift_lower_bound": lower,
        "forward_uplift_upper_bound": upper,
    }
    # The monitor wakes often so it can notice new outcomes promptly. Do not turn those wakeups
    # into redundant SQLite writes when the evidence itself has not changed.
    if all(getattr(hypothesis, field) == value for field, value in evidence.items()):
        return hypothesis
    return hypothesis.model_copy(update={"updated_at": now, "last_evaluated_at": now, **evidence})


def _condition_matches(
    observation: LearningObservation,
    feature: str,
    operator: str,
    threshold: float,
) -> bool:
    value = observation.features.get(feature)
    if value is None or not math.isfinite(value):
        return False
    return value <= threshold if operator == "<=" else value >= threshold


def _signature(
    kind: CoachExperimentKind,
    mode: RiskMode,
    fingerprint: str,
    feature: str | None,
    operator: str | None,
    threshold: float | None,
    hold_seconds: int | None,
) -> str:
    payload = {
        "kind": kind.value,
        "risk_mode": mode.value,
        "configuration_fingerprint": fingerprint,
        "feature": feature,
        "operator": operator,
        "threshold": threshold,
        "hold_seconds": hold_seconds,
        "schema": COACH_SCHEMA_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _selection_schema(candidate_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string", "enum": ["none", *candidate_ids]},
            "summary": {"type": "string", "maxLength": 240},
        },
        "required": ["candidate_id", "summary"],
        "additionalProperties": False,
    }


def _hypothesis_from_candidate(
    review: CoachReview,
    candidate: _Candidate,
    summary: str,
) -> CoachHypothesis:
    now = review.created_at
    return CoachHypothesis(
        hypothesis_id="coach-hypothesis-" + uuid.uuid4().hex,
        signature=candidate.signature,
        coach_review_id=review.review_id,
        created_at=now,
        updated_at=now,
        cutoff_at=review.cutoff_at,
        kind=candidate.kind,
        title=candidate.title,
        rationale=_clean_text(summary, 240) or "Selected for a new forward-only Shadow test.",
        risk_mode=review.risk_mode,
        configuration_fingerprint=review.configuration_fingerprint,
        model_name=review.model_name,
        model_digest=review.model_digest,
        feature_name=candidate.feature_name,
        operator=candidate.operator,  # type: ignore[arg-type]
        threshold=candidate.threshold,
        hold_seconds=candidate.hold_seconds,
        discovery_observed_count=candidate.observed_count,
        discovery_usable_count=candidate.usable_count,
        discovery_availability_fraction=candidate.availability_fraction,
        discovery_mean_uplift=candidate.mean_uplift,
        discovery_uplift_lower_bound=candidate.uplift_lower_bound,
        minimum_forward_samples=COACH_MINIMUM_FORWARD_SAMPLES,
        minimum_availability_fraction=COACH_MINIMUM_AVAILABILITY,
        influence_applied=False,
    )


def _review_without_candidate(
    *,
    now: datetime,
    outcomes_seen: int,
    mode: RiskMode,
    fingerprint: str,
    model_name: str,
    model_digest: str,
) -> CoachReview:
    return CoachReview(
        review_id="coach-review-" + uuid.uuid4().hex,
        created_at=now,
        cutoff_at=now,
        outcomes_seen=outcomes_seen,
        risk_mode=mode,
        configuration_fingerprint=fingerprint,
        model_name=model_name,
        model_digest=model_digest,
        prompt_version=COACH_PROMPT_VERSION,
        schema_version=COACH_SCHEMA_VERSION,
        input_sha256=hashlib.sha256(b"no-bounded-candidate").hexdigest(),
        candidate_count=0,
        latency_ms=0,
        valid=True,
        selected_candidate_id="none",
        summary="No bounded experiment cleared the historical screening floor yet.",
    )


def _failed_review(
    *,
    now: datetime,
    outcomes_seen: int,
    mode: RiskMode,
    fingerprint: str,
    model_name: str,
    model_digest: str,
    input_sha256: str,
    candidate_count: int,
    reason: str,
) -> CoachReview:
    return CoachReview(
        review_id="coach-review-" + uuid.uuid4().hex,
        created_at=now,
        cutoff_at=now,
        outcomes_seen=outcomes_seen,
        risk_mode=mode,
        configuration_fingerprint=fingerprint,
        model_name=model_name,
        model_digest=model_digest,
        prompt_version=COACH_PROMPT_VERSION,
        schema_version=COACH_SCHEMA_VERSION,
        input_sha256=input_sha256,
        candidate_count=candidate_count,
        latency_ms=0,
        valid=False,
        summary="The optional coach was unavailable; the trading engine was unaffected.",
        failure_reason=reason,
    )


def _clean_text(value: str, limit: int) -> str:
    printable = "".join(character for character in value if character.isprintable())
    return " ".join(printable.split())[:limit]
