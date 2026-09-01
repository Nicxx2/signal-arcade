from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .database import Database
from .intelligence.learning import (
    COACH_ENTRY_RULES,
    COACH_MANIPULATION_COMBINATIONS,
    COACH_MANIPULATION_RULES,
    FEATURE_SCHEMA_VERSION,
    LEARNING_HORIZONS_SECONDS,
    PRIMARY_HORIZON_SECONDS,
    SIZING_MULTIPLIERS,
)
from .models import (
    RISK_LIMITS,
    ChallengerSkill,
    CoachCondition,
    CoachExperimentKind,
    CoachExperimentState,
    CoachHypothesis,
    CoachReview,
    DecisionAction,
    LearningObservation,
    RiskMode,
)
from .providers.http import HttpProviders
from .strategy import LEARNABLE_BASELINE_VERSIONS

logger = logging.getLogger(__name__)

COACH_PROMPT_VERSION = "coach-research-v4"
COACH_SCHEMA_VERSION = "coach-research-schema-v4"
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
COACH_OBSERVATION_WINDOW = 5_000
COACH_MAX_CANDIDATES = 6
COACH_Z_SCORE = 1.96
COACH_MINIMUM_SAMPLES_PER_SEASON = 10
COACH_MAXIMUM_FORWARD_OBSERVED = 180
COACH_MAXIMUM_FORWARD_DAYS = 90

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
    "microtrade_count_ratio": "dust-sized trades dominate activity",
    "meaningful_volume_ratio": "little volume is economically meaningful",
    "meaningful_wallet_ratio": "few wallets contribute meaningful value",
    "median_trade_quote_sol": "the median trade is exceptionally small",
    "price_path_efficiency": "price travel creates little durable progress",
    "rapid_price_reversal_ratio": "the price reverses unusually often",
    "trade_density_5m": "trade density is exceptionally high",
}


class _CoachSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(max_length=80)
    summary: str = Field(max_length=240)


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    signature: str
    kind: CoachExperimentKind
    skill: ChallengerSkill
    title: str
    feature_name: str | None
    operator: str | None
    threshold: float | None
    conditions: tuple[CoachCondition, ...]
    hold_seconds: int | None
    baseline_hold_seconds: int | None
    size_multiplier: float | None
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
            "skill": self.skill.value,
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
        provenance: Callable[[], dict[str, Any]] | None = None,
        contribution_enabled: Callable[[], bool] | None = None,
    ) -> None:
        self.database = database
        self.http = http
        self.enabled = enabled
        self.context = context
        self.outcomes_seen = outcomes_seen
        self.model_provenance = model_provenance
        self.can_run = can_run
        self.provenance = provenance
        self.contribution_enabled = contribution_enabled or (lambda: False)
        self._lock = threading.RLock()
        self.task: asyncio.Task[None] | None = None
        self.busy = False
        self.last_error: str | None = None
        self.paused_reason: str | None = None
        self.last_attempt_at: datetime | None = None
        self.next_attempt_at: datetime | None = None
        self.context_outcomes_seen = 0
        self.reviews = database.list_coach_reviews(25)
        self.hypotheses = database.list_coach_hypotheses(100)

    def _context_provenance(self) -> dict[str, Any]:
        mode, fingerprint = self.context()
        supplied = self.provenance() if self.provenance is not None else {}
        dependencies = supplied.get("dependency_versions", {})
        return {
            "risk_mode": mode,
            "configuration_fingerprint": fingerprint,
            "baseline_version": str(supplied.get("baseline_version") or "baseline-v1.1"),
            "feature_schema_version": str(
                supplied.get("feature_schema_version") or "challenger-features-v1"
            ),
            "dependency_versions": (
                {str(key): str(value) for key, value in dependencies.items()}
                if isinstance(dependencies, dict)
                else {}
            ),
            "baseline_hold_seconds": int(
                supplied.get("baseline_hold_seconds") or RISK_LIMITS[mode].max_hold_seconds
            ),
        }

    @staticmethod
    def _matches_provenance(item: CoachHypothesis | CoachReview, context: dict[str, Any]) -> bool:
        return bool(
            item.risk_mode == context["risk_mode"]
            and item.configuration_fingerprint == context["configuration_fingerprint"]
            and item.baseline_version == context["baseline_version"]
            and item.feature_schema_version == context["feature_schema_version"]
            and item.dependency_versions == context["dependency_versions"]
        )

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
        observations = await asyncio.to_thread(
            self.database.recent_learning_observations,
            COACH_OBSERVATION_WINDOW,
        )
        await asyncio.to_thread(self._refresh_hypotheses, now, observations)
        context = self._context_provenance()
        mode = context["risk_mode"]
        fingerprint = context["configuration_fingerprint"]
        active = self._active_hypothesis(context)
        if active is not None:
            self.paused_reason = "forward_test_in_progress"
            return
        exact_seen = _context_outcomes_seen(observations, context)
        # The fallback keeps the standalone v2 constructor contract used by older integrations;
        # production supplies exact provenance and therefore never uses a global cohort count.
        seen = max(exact_seen, self.outcomes_seen())
        self.context_outcomes_seen = seen
        last_seen = max(
            (
                review.outcomes_seen
                for review in self.reviews
                if review.valid and self._matches_provenance(review, context)
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
            excluded = {
                item.signature
                for item in self.hypotheses
                if self._matches_provenance(item, context)
            }
            candidates = _build_candidates(
                observations,
                mode,
                fingerprint,
                excluded,
                baseline_version=context["baseline_version"],
                feature_schema_version=context["feature_schema_version"],
                dependency_versions=context["dependency_versions"],
                baseline_hold_seconds=context["baseline_hold_seconds"],
            )
            candidates = _fair_lane_candidates(
                candidates,
                [item for item in self.hypotheses if self._matches_provenance(item, context)],
            )
            model_name, model_digest = self.model_provenance()
            if not candidates:
                review = _review_without_candidate(
                    now=now,
                    outcomes_seen=seen,
                    mode=mode,
                    fingerprint=fingerprint,
                    baseline_version=context["baseline_version"],
                    feature_schema_version=context["feature_schema_version"],
                    dependency_versions=context["dependency_versions"],
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
            # A pause may arrive while a slow CPU inference is in flight. Discard that optional
            # result instead of allowing a proposal to appear after the user paused research.
            if not self.enabled():
                self.paused_reason = "research_paused_during_review"
                return
            current_context = self._context_provenance()
            if current_context != context:
                self.last_error = "context_changed_during_review"
                self.next_attempt_at = now + timedelta(seconds=COACH_RETRY_SECONDS)
                return
            if response is None:
                review = _failed_review(
                    now=now,
                    outcomes_seen=seen,
                    mode=mode,
                    fingerprint=fingerprint,
                    baseline_version=context["baseline_version"],
                    feature_schema_version=context["feature_schema_version"],
                    dependency_versions=context["dependency_versions"],
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
                baseline_version=context["baseline_version"],
                feature_schema_version=context["feature_schema_version"],
                dependency_versions=context["dependency_versions"],
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
            if not valid:
                await asyncio.to_thread(self._save_review, review)
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
                await asyncio.to_thread(self._save_selection, review, hypothesis)
            else:
                await asyncio.to_thread(self._save_review, review)
        finally:
            self.busy = False

    def _save_review(self, review: CoachReview) -> None:
        self.database.save_coach_review(review)
        with self._lock:
            retained = [item for item in self.reviews if item.review_id != review.review_id]
            self.reviews = [review, *retained][:25]
        self.database.prune_coach_history()

    def _save_hypothesis(self, hypothesis: CoachHypothesis) -> None:
        self.database.save_coach_hypothesis(hypothesis)
        with self._lock:
            self.hypotheses = [
                hypothesis,
                *[
                    item
                    for item in self.hypotheses
                    if item.hypothesis_id != hypothesis.hypothesis_id
                ],
            ][:100]

    def _save_selection(self, review: CoachReview, hypothesis: CoachHypothesis) -> None:
        if not self.database.save_coach_selection(review, hypothesis):
            return
        with self._lock:
            self.reviews = [
                review,
                *[item for item in self.reviews if item.review_id != review.review_id],
            ][:25]
            self.hypotheses = [
                hypothesis,
                *[
                    item
                    for item in self.hypotheses
                    if item.hypothesis_id != hypothesis.hypothesis_id
                ],
            ][:100]
        self.database.prune_coach_history()

    def _refresh_hypotheses(
        self,
        now: datetime,
        observations: Sequence[LearningObservation] | None = None,
    ) -> None:
        if not self.hypotheses:
            return
        selected = (
            list(observations)
            if observations is not None
            else self.database.recent_learning_observations(COACH_OBSERVATION_WINDOW)
        )
        refreshed: list[CoachHypothesis] = []
        for hypothesis in self.hypotheses:
            updated = _evaluate_hypothesis(hypothesis, selected, now)
            if updated != hypothesis:
                self.database.save_coach_hypothesis(updated)
            refreshed.append(updated)
        with self._lock:
            self.hypotheses = refreshed

    def _current_hypothesis(self, context: dict[str, Any]) -> CoachHypothesis | None:
        return next(
            (item for item in self.hypotheses if self._matches_provenance(item, context)),
            None,
        )

    def _active_hypothesis(self, context: dict[str, Any]) -> CoachHypothesis | None:
        current = self._current_hypothesis(context)
        return (
            current
            if current is not None and current.state == CoachExperimentState.TESTING
            else None
        )

    def status(self) -> dict[str, Any]:
        context = self._context_provenance()
        seen = max(self.context_outcomes_seen, max(0, self.outcomes_seen()))
        current = self._current_hypothesis(context)
        active = self._active_hypothesis(context)
        contribution_candidate = next(
            (
                item
                for item in self.hypotheses
                if self._matches_provenance(item, context)
                and item.state == CoachExperimentState.PROMISING
                and item.contribution_state in {"ready", "waiting_for_champion"}
            ),
            None,
        )
        last_valid_seen = max(
            (
                review.outcomes_seen
                for review in self.reviews
                if review.valid and self._matches_provenance(review, context)
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
            else current.state.value
            if current is not None
            else "waiting"
        )
        qualification_gates = _coach_qualification_gates(current)
        recent_hypotheses = []
        for item in self.hypotheses[:6]:
            view = item.model_dump(mode="json")
            view["context_active"] = bool(self._matches_provenance(item, context))
            recent_hypotheses.append(view)
        return {
            "mode": "shadow" if self.enabled() else "off",
            "research_enabled": self.enabled(),
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
            "minimum_samples_per_season": COACH_MINIMUM_SAMPLES_PER_SEASON,
            "contribution_enabled": bool(self.contribution_enabled()),
            "contribution_ready": contribution_candidate is not None,
            "contribution_candidate": (
                {
                    "hypothesis_id": contribution_candidate.hypothesis_id,
                    "title": contribution_candidate.title,
                    "skill": contribution_candidate.skill.value,
                    "state": contribution_candidate.contribution_state,
                }
                if contribution_candidate is not None
                else None
            ),
            "research_lanes": _research_lane_status(self.hypotheses, context),
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

    def ready_contribution(self) -> CoachHypothesis | None:
        """Return one supported current-context study without mutating trading state."""

        if not self.contribution_enabled():
            return None
        context = self._context_provenance()
        with self._lock:
            candidates = [
                item
                for item in self.hypotheses
                if self._matches_provenance(item, context)
                and item.state == CoachExperimentState.PROMISING
                and item.contribution_state in {"ready", "waiting_for_champion"}
            ]
            # Give every newly supported idea one handoff attempt before retrying a study whose
            # skill has no Champion yet. This prevents one unavailable lane starving the others.
            selected = next(
                (item for item in candidates if item.contribution_state == "ready"),
                candidates[0] if candidates else None,
            )
            return selected.model_copy(deep=True) if selected is not None else None

    def mark_contribution(
        self,
        hypothesis_id: str,
        state: str,
        artifact_version: str | None = None,
    ) -> None:
        allowed = {"waiting_for_champion", "handed_off", "stale"}
        if state not in allowed:
            raise ValueError("unsupported Coach contribution state")
        with self._lock:
            hypothesis = next(
                (item for item in self.hypotheses if item.hypothesis_id == hypothesis_id),
                None,
            )
            if hypothesis is None:
                return
            updated = hypothesis.model_copy(
                update={
                    "updated_at": datetime.now(UTC),
                    "contribution_state": state,
                    "contributed_artifact_version": artifact_version,
                }
            )
            self.hypotheses = [
                updated if item.hypothesis_id == hypothesis_id else item for item in self.hypotheses
            ]
        self.database.save_coach_hypothesis(updated)


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
    *,
    baseline_version: str = "baseline-v1.1",
    feature_schema_version: str = "challenger-features-v1",
    dependency_versions: dict[str, str] | None = None,
    baseline_hold_seconds: int | None = None,
) -> list[_Candidate]:
    dependencies = dependency_versions or {}
    context_rows = [
        item
        for item in observations
        if item.risk_mode == mode
        and item.configuration_fingerprint == fingerprint
        and item.baseline_version == baseline_version
        and item.feature_schema_version == feature_schema_version
        and item.active_skill_versions == dependencies
    ]
    actionable_entries = [
        item
        for item in context_rows
        if item.baseline_action == DecisionAction.ENTER and item.baseline_actionable
    ]
    candidates: list[_Candidate] = []
    for feature, operator, threshold in COACH_ENTRY_RULES:
        entry_conditions = (
            CoachCondition(feature_name=feature, operator=operator, threshold=threshold),
        )
        signature = _signature(
            CoachExperimentKind.ENTRY_VETO,
            mode,
            fingerprint,
            conditions=entry_conditions,
            baseline_version=baseline_version,
            feature_schema_version=feature_schema_version,
            dependency_versions=dependencies,
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
                skill=ChallengerSkill.ENTRY,
                title=f"Test preserving cash when {label}",
                feature_name=feature,
                operator=operator,
                threshold=threshold,
                conditions=entry_conditions,
                hold_seconds=None,
                baseline_hold_seconds=None,
                size_multiplier=None,
                observed_count=observed,
                usable_count=usable,
                availability_fraction=availability,
                mean_uplift=mean,
                uplift_lower_bound=lower,
                uplift_upper_bound=upper,
            )
        )

    manipulation_rules: list[tuple[CoachCondition, ...]] = [
        (CoachCondition(feature_name=feature, operator=operator, threshold=threshold),)
        for feature, operator, threshold in COACH_MANIPULATION_RULES
    ]
    manipulation_rules.extend(
        tuple(
            CoachCondition(feature_name=feature, operator=operator, threshold=threshold)
            for feature, operator, threshold in pair
        )
        for pair in COACH_MANIPULATION_COMBINATIONS
    )
    for conditions in manipulation_rules:
        signature = _signature(
            CoachExperimentKind.MANIPULATION_VETO,
            mode,
            fingerprint,
            conditions=conditions,
            baseline_version=baseline_version,
            feature_schema_version=feature_schema_version,
            dependency_versions=dependencies,
        )
        if signature in excluded_signatures:
            continue
        matched = [item for item in actionable_entries if _conditions_match(item, conditions)]
        stats = _entry_stats(matched)
        if (
            stats is None
            or stats[1] < COACH_MINIMUM_DISCOVERY_SAMPLES
            or stats[2] < COACH_MINIMUM_AVAILABILITY
            or stats[4] <= 0
        ):
            continue
        observed, usable, availability, mean, lower, upper = stats
        labels = " and ".join(_FEATURE_LABELS[item.feature_name] for item in conditions)
        candidates.append(
            _Candidate(
                candidate_id="candidate-" + signature[:16],
                signature=signature,
                kind=CoachExperimentKind.MANIPULATION_VETO,
                skill=ChallengerSkill.MANIPULATION,
                title=f"Test avoiding entries when {labels}",
                feature_name=conditions[0].feature_name if len(conditions) == 1 else None,
                operator=conditions[0].operator if len(conditions) == 1 else None,
                threshold=conditions[0].threshold if len(conditions) == 1 else None,
                conditions=conditions,
                hold_seconds=None,
                baseline_hold_seconds=None,
                size_multiplier=None,
                observed_count=observed,
                usable_count=usable,
                availability_fraction=availability,
                mean_uplift=mean,
                uplift_lower_bound=lower,
                uplift_upper_bound=upper,
            )
        )

    for multiplier in SIZING_MULTIPLIERS:
        if multiplier == 1.0:
            continue
        signature = _signature(
            CoachExperimentKind.SIZING_MULTIPLIER,
            mode,
            fingerprint,
            size_multiplier=multiplier,
            baseline_version=baseline_version,
            feature_schema_version=feature_schema_version,
            dependency_versions=dependencies,
        )
        if signature in excluded_signatures:
            continue
        stats = _sizing_stats(actionable_entries, multiplier)
        if (
            stats is None
            or stats[1] < COACH_MINIMUM_DISCOVERY_SAMPLES
            or stats[2] < COACH_MINIMUM_AVAILABILITY
            or stats[4] <= 0
        ):
            continue
        observed, usable, availability, mean, lower, upper = stats
        candidates.append(
            _Candidate(
                candidate_id="candidate-" + signature[:16],
                signature=signature,
                kind=CoachExperimentKind.SIZING_MULTIPLIER,
                skill=ChallengerSkill.SIZING,
                title=f"Test a bounded {multiplier:g}x paper size",
                feature_name=None,
                operator=None,
                threshold=None,
                conditions=(),
                hold_seconds=None,
                baseline_hold_seconds=None,
                size_multiplier=multiplier,
                observed_count=observed,
                usable_count=usable,
                availability_fraction=availability,
                mean_uplift=mean,
                uplift_lower_bound=lower,
                uplift_upper_bound=upper,
            )
        )

    baseline_hold = baseline_hold_seconds or RISK_LIMITS[mode].max_hold_seconds
    for horizon in LEARNING_HORIZONS_SECONDS:
        if horizon >= baseline_hold:
            continue
        signature = _signature(
            CoachExperimentKind.EARLIER_REVIEW,
            mode,
            fingerprint,
            hold_seconds=horizon,
            baseline_hold_seconds=baseline_hold,
            baseline_version=baseline_version,
            feature_schema_version=feature_schema_version,
            dependency_versions=dependencies,
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
                skill=ChallengerSkill.EXIT,
                title=f"Test reviewing normal holds at {horizon // 60}m",
                feature_name=None,
                operator=None,
                threshold=None,
                conditions=(),
                hold_seconds=horizon,
                baseline_hold_seconds=baseline_hold,
                size_multiplier=None,
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
    return candidates


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


def _coach_size_value(
    observation: LearningObservation,
    multiplier: float,
) -> float | None:
    trial = observation.size_trials.get(f"{multiplier:g}")
    baseline = observation.size_trials.get("1")
    if (
        trial is None
        or baseline is None
        or not trial.eligible_at_entry
        or trial.entry_cost_lamports is None
        or baseline.entry_cost_lamports is None
        or baseline.entry_cost_lamports <= 0
    ):
        return None
    checkpoint = trial.checkpoints.get(str(PRIMARY_HORIZON_SECONDS))
    if checkpoint is None or checkpoint.exit_value_lamports is None:
        return None
    return (checkpoint.exit_value_lamports - trial.entry_cost_lamports) / (
        baseline.entry_cost_lamports
    )


def _sizing_stats(
    observations: Sequence[LearningObservation],
    multiplier: float,
) -> tuple[int, int, float, float, float, float] | None:
    primary = str(PRIMARY_HORIZON_SECONDS)
    observed = [
        item
        for item in observations
        if (selected_trial := item.size_trials.get(f"{multiplier:g}")) is not None
        and (baseline_trial := item.size_trials.get("1")) is not None
        and primary in selected_trial.checkpoints
        and primary in baseline_trial.checkpoints
    ]
    values: list[float] = []
    for item in observed:
        selected_value = _coach_size_value(item, multiplier)
        baseline_value = _coach_size_value(item, 1.0)
        if selected_value is not None and baseline_value is not None:
            values.append(selected_value - baseline_value)
    return _stats(len(observed), values)


def _fair_lane_candidates(
    candidates: Sequence[_Candidate],
    history: Sequence[CoachHypothesis],
) -> list[_Candidate]:
    """Rotate research lanes so one rich signal family cannot monopolize the Coach."""

    order = [
        ChallengerSkill.ENTRY,
        ChallengerSkill.MANIPULATION,
        ChallengerSkill.SIZING,
        ChallengerSkill.EXIT,
    ]
    last_skill = history[0].skill if history else ChallengerSkill.EXIT
    start = (order.index(last_skill) + 1) % len(order)
    for offset in range(len(order)):
        skill = order[(start + offset) % len(order)]
        selected = [item for item in candidates if item.skill == skill]
        if selected:
            return selected[:COACH_MAX_CANDIDATES]
    return []


def _context_outcomes_seen(
    observations: Sequence[LearningObservation],
    context: dict[str, Any],
) -> int:
    primary = str(PRIMARY_HORIZON_SECONDS)
    return sum(
        primary in item.checkpoints
        and item.checkpoints[primary].net_return is not None
        and item.risk_mode == context["risk_mode"]
        and item.configuration_fingerprint == context["configuration_fingerprint"]
        and item.baseline_version == context["baseline_version"]
        and item.feature_schema_version == context["feature_schema_version"]
        and item.active_skill_versions == context["dependency_versions"]
        for item in observations
    )


def _research_lane_status(
    hypotheses: Sequence[CoachHypothesis],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    labels = {
        ChallengerSkill.ENTRY: "Entry",
        ChallengerSkill.MANIPULATION: "Manipulation",
        ChallengerSkill.SIZING: "Sizing",
        ChallengerSkill.EXIT: "Exit",
    }
    result = []
    for skill, label in labels.items():
        history = [
            item
            for item in hypotheses
            if item.skill == skill
            and item.risk_mode == context["risk_mode"]
            and item.configuration_fingerprint == context["configuration_fingerprint"]
            and item.baseline_version == context["baseline_version"]
            and item.feature_schema_version == context["feature_schema_version"]
            and item.dependency_versions == context["dependency_versions"]
        ]
        current = history[0] if history else None
        supported = next(
            (item for item in history if item.state == CoachExperimentState.PROMISING),
            None,
        )
        result.append(
            {
                "skill": skill.value,
                "label": label,
                "state": current.state.value if current is not None else "observing",
                "current_title": current.title if current is not None else None,
                "best_title": supported.title if supported is not None else None,
                "studies": len(history),
                "supported_studies": sum(
                    item.state == CoachExperimentState.PROMISING for item in history
                ),
            }
        )
    return result


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
        CoachExperimentState.PROMISING,
        CoachExperimentState.INCONCLUSIVE,
        CoachExperimentState.NOT_SUPPORTED,
    }:
        return hypothesis

    rows = sorted(
        (
            item
            for item in observations
            if item.created_at > hypothesis.cutoff_at
            and item.risk_mode == hypothesis.risk_mode
            and item.configuration_fingerprint == hypothesis.configuration_fingerprint
            and item.baseline_version == hypothesis.baseline_version
            and item.feature_schema_version == hypothesis.feature_schema_version
            and item.active_skill_versions == hypothesis.dependency_versions
        ),
        key=lambda item: item.created_at,
    )
    seen_ids = set(hypothesis.forward_observation_ids)
    observation_ids = list(hypothesis.forward_observation_ids)
    values = list(hypothesis.forward_values)
    season_counts = dict(hypothesis.forward_season_counts)
    for item in rows:
        if item.observation_id in seen_ids:
            continue
        resolved, relevant, value = _hypothesis_observation_value(hypothesis, item)
        if not relevant or not resolved:
            continue
        seen_ids.add(item.observation_id)
        observation_ids.append(item.observation_id)
        if value is not None:
            values.append(value)
            if item.season_id:
                season_counts[item.season_id] = season_counts.get(item.season_id, 0) + 1
        if len(observation_ids) >= COACH_MAXIMUM_FORWARD_OBSERVED:
            break

    observed = len(observation_ids)
    usable = len(values)
    availability = usable / observed if observed else 0.0
    mean = lower = upper = None
    if values:
        mean, lower, upper = _mean_bounds(values)
    meaningful_seasons = sum(
        count >= COACH_MINIMUM_SAMPLES_PER_SEASON for count in season_counts.values()
    )
    state = CoachExperimentState.TESTING
    resolution_reason: str | None = None
    if (
        usable >= hypothesis.minimum_forward_samples
        and availability >= hypothesis.minimum_availability_fraction
        and meaningful_seasons >= COACH_MINIMUM_FORWARD_SEASONS
        and lower is not None
        and lower > COACH_MINIMUM_UPLIFT
    ):
        state = CoachExperimentState.PROMISING
        resolution_reason = "forward_proof_supported"
    elif usable >= COACH_REJECTION_SAMPLES and upper is not None and upper <= 0:
        state = CoachExperimentState.NOT_SUPPORTED
        resolution_reason = "forward_evidence_not_supported"
    elif observed >= COACH_MAXIMUM_FORWARD_OBSERVED:
        state = CoachExperimentState.INCONCLUSIVE
        resolution_reason = "maximum_forward_evidence_reached"
    elif now - hypothesis.created_at >= timedelta(days=COACH_MAXIMUM_FORWARD_DAYS):
        state = CoachExperimentState.INCONCLUSIVE
        resolution_reason = "forward_study_expired"
    terminal = state != CoachExperimentState.TESTING
    contribution_state = hypothesis.contribution_state
    if (
        state == CoachExperimentState.PROMISING
        and hypothesis.baseline_version in LEARNABLE_BASELINE_VERSIONS
        and hypothesis.feature_schema_version == FEATURE_SCHEMA_VERSION
        and contribution_state == "research_only"
    ):
        contribution_state = "ready"
    evidence = {
        "state": state,
        "forward_observed_count": observed,
        "forward_usable_count": usable,
        "forward_availability_fraction": availability,
        "forward_season_count": meaningful_seasons,
        "forward_mean_uplift": mean,
        "forward_uplift_lower_bound": lower,
        "forward_uplift_upper_bound": upper,
        "forward_observation_ids": observation_ids,
        "forward_values": values,
        "forward_season_counts": season_counts,
        "resolved_at": now if terminal else None,
        "resolution_reason": resolution_reason,
        "contribution_state": contribution_state,
    }
    # The monitor wakes often so it can notice new outcomes promptly. Do not turn those wakeups
    # into redundant SQLite writes when the evidence itself has not changed.
    if all(getattr(hypothesis, field) == value for field, value in evidence.items()):
        return hypothesis
    return hypothesis.model_copy(update={"updated_at": now, "last_evaluated_at": now, **evidence})


def _hypothesis_observation_value(
    hypothesis: CoachHypothesis,
    observation: LearningObservation,
) -> tuple[bool, bool, float | None]:
    if observation.baseline_action != DecisionAction.ENTER or not observation.baseline_actionable:
        return False, False, None
    skill = _skill_for_kind(hypothesis.kind)
    if skill in {ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION}:
        conditions = tuple(hypothesis.conditions)
        if not conditions and (
            hypothesis.feature_name is None
            or hypothesis.operator is None
            or hypothesis.threshold is None
        ):
            return False, False, None
        if conditions:
            matches = _conditions_match(observation, conditions)
        else:
            matches = _condition_matches(
                observation,
                hypothesis.feature_name or "",
                hypothesis.operator or "<=",
                hypothesis.threshold or 0.0,
            )
        if not matches:
            return False, False, None
        checkpoint = observation.checkpoints.get(str(PRIMARY_HORIZON_SECONDS))
        if checkpoint is None:
            return False, True, None
        return True, True, -checkpoint.net_return if checkpoint.net_return is not None else None
    if skill == ChallengerSkill.SIZING:
        multiplier = hypothesis.size_multiplier
        if multiplier is None:
            return False, False, None
        trial = observation.size_trials.get(f"{multiplier:g}")
        baseline_trial = observation.size_trials.get("1")
        if trial is None or baseline_trial is None:
            return True, True, None
        primary = str(PRIMARY_HORIZON_SECONDS)
        if primary not in trial.checkpoints or primary not in baseline_trial.checkpoints:
            return False, True, None
        selected_value = _coach_size_value(observation, multiplier)
        baseline_value = _coach_size_value(observation, 1.0)
        return (
            True,
            True,
            selected_value - baseline_value
            if selected_value is not None and baseline_value is not None
            else None,
        )
    selected = hypothesis.hold_seconds
    baseline_horizon = (
        hypothesis.baseline_hold_seconds or RISK_LIMITS[hypothesis.risk_mode].max_hold_seconds
    )
    if selected is None:
        return False, False, None
    selected_checkpoint = observation.checkpoints.get(str(selected))
    baseline_checkpoint = observation.checkpoints.get(str(baseline_horizon))
    if selected_checkpoint is None or baseline_checkpoint is None:
        return False, True, None
    return (
        True,
        True,
        selected_checkpoint.net_return - baseline_checkpoint.net_return
        if selected_checkpoint.net_return is not None and baseline_checkpoint.net_return is not None
        else None,
    )


def _skill_for_kind(kind: CoachExperimentKind) -> ChallengerSkill:
    return {
        CoachExperimentKind.ENTRY_VETO: ChallengerSkill.ENTRY,
        CoachExperimentKind.MANIPULATION_VETO: ChallengerSkill.MANIPULATION,
        CoachExperimentKind.SIZING_MULTIPLIER: ChallengerSkill.SIZING,
        CoachExperimentKind.EARLIER_REVIEW: ChallengerSkill.EXIT,
    }[kind]


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


def _conditions_match(
    observation: LearningObservation,
    conditions: Sequence[CoachCondition],
) -> bool:
    return bool(conditions) and all(
        _condition_matches(
            observation,
            condition.feature_name,
            condition.operator,
            condition.threshold,
        )
        for condition in conditions
    )


def _signature(
    kind: CoachExperimentKind,
    mode: RiskMode,
    fingerprint: str,
    *,
    conditions: Sequence[CoachCondition] = (),
    hold_seconds: int | None = None,
    baseline_hold_seconds: int | None = None,
    size_multiplier: float | None = None,
    baseline_version: str = "baseline-v1.1",
    feature_schema_version: str = "challenger-features-v1",
    dependency_versions: dict[str, str] | None = None,
) -> str:
    payload = {
        "kind": kind.value,
        "risk_mode": mode.value,
        "configuration_fingerprint": fingerprint,
        "conditions": [condition.model_dump(mode="json") for condition in conditions],
        "hold_seconds": hold_seconds,
        "baseline_hold_seconds": baseline_hold_seconds,
        "size_multiplier": size_multiplier,
        "baseline_version": baseline_version,
        "feature_schema_version": feature_schema_version,
        "dependency_versions": dependency_versions or {},
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
        skill=candidate.skill,
        title=candidate.title,
        rationale=_clean_text(summary, 240) or "Selected for a new forward-only Shadow test.",
        risk_mode=review.risk_mode,
        configuration_fingerprint=review.configuration_fingerprint,
        baseline_version=review.baseline_version,
        feature_schema_version=review.feature_schema_version,
        dependency_versions=dict(review.dependency_versions),
        model_name=review.model_name,
        model_digest=review.model_digest,
        feature_name=candidate.feature_name,
        operator=candidate.operator,  # type: ignore[arg-type]
        threshold=candidate.threshold,
        conditions=list(candidate.conditions),
        hold_seconds=candidate.hold_seconds,
        baseline_hold_seconds=candidate.baseline_hold_seconds,
        size_multiplier=candidate.size_multiplier,
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
    baseline_version: str,
    feature_schema_version: str,
    dependency_versions: dict[str, str],
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
        baseline_version=baseline_version,
        feature_schema_version=feature_schema_version,
        dependency_versions=dependency_versions,
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
    baseline_version: str,
    feature_schema_version: str,
    dependency_versions: dict[str, str],
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
        baseline_version=baseline_version,
        feature_schema_version=feature_schema_version,
        dependency_versions=dependency_versions,
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
