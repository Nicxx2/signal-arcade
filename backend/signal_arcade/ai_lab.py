from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import Settings
from .database import Database
from .intelligence.features import TokenState
from .models import (
    RISK_LIMITS,
    AiCriticAssessment,
    AiCriticVerdict,
    AiDecisionMode,
    Decision,
    DecisionAction,
)
from .paper.curve_math import quote_buy, quote_sell
from .providers.http import HttpProviders, ProviderError
from .redaction import redact_secrets

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-critic-v3"
SCHEMA_VERSION = "ai-critic-schema-v3"
MINIMUM_RESOLVED_ASSESSMENTS = 200
MINIMUM_VETO_OUTCOMES = 20
MAX_GUARDED_P95_LATENCY_MS = 2_500
MINIMUM_VALID_FRACTION = 0.99
QUALIFICATION_Z_SCORE = 1.96
PRIMARY_OUTCOME_SECONDS = 300
SHADOW_QUEUE_CAPACITY = 8
MAX_SHADOW_QUEUE_AGE_SECONDS = 60
MAX_MODEL_PULL_ATTEMPTS = 3
MODEL_PULL_RETRY_BASE_SECONDS = 2

RISK_FLAGS = {
    "concentration",
    "coordination",
    "creator_activity",
    "liquidity",
    "momentum_extreme",
    "drawdown",
    "data_quality",
    "cost_edge",
    "none",
}

MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "qwen3.5:2b",
        "label": "Qwen 3.5 · 2B",
        "download_bytes": 2_700_000_000,
        "recommended_ram_gb": 8,
        "role": "Recommended for CPU-only mini PCs",
    },
    {
        "name": "phi4-mini:3.8b",
        "label": "Phi-4 Mini · 3.8B",
        "download_bytes": 2_500_000_000,
        "recommended_ram_gb": 16,
        "role": "Compact Shadow critic",
    },
    {
        "name": "qwen3.5:4b",
        "label": "Qwen 3.5 · 4B",
        "download_bytes": 3_400_000_000,
        "recommended_ram_gb": 16,
        "role": "Higher-quality critic when measured latency allows",
    },
    {
        "name": "qwen3.5:9b",
        "label": "Qwen 3.5 · 9B",
        "download_bytes": 6_600_000_000,
        "recommended_ram_gb": 32,
        "role": "Higher-quality critic when latency allows",
    },
    {
        "name": "qwen3.5:27b",
        "label": "Qwen 3.5 · 27B",
        "download_bytes": 17_000_000_000,
        "recommended_ram_gb": 64,
        "role": "Large-system experiment",
    },
)


class _CriticPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["support", "veto", "insufficient_evidence"]
    confidence: Literal["low", "medium", "high"]
    evidence_refs: list[str] = Field(max_length=2)
    risk_flags: list[str] = Field(max_length=2)


class AiDecisionLab:
    """Optional local-LLM critic that must prove a veto-only paper benefit."""

    def __init__(
        self,
        database: Database,
        http: HttpProviders,
        settings: Settings,
        *,
        select_model: Callable[[str], None],
        configuration_fingerprint: Callable[[], str],
    ) -> None:
        self.database = database
        self.http = http
        self.settings = settings
        self.select_model = select_model
        self.configuration_fingerprint = configuration_fingerprint
        try:
            self.mode = AiDecisionMode(
                database.get_setting("ai_decision_mode", AiDecisionMode.OFF.value)
            )
        except ValueError:
            self.mode = AiDecisionMode.OFF
            database.set_setting("ai_decision_mode", self.mode.value)
        self.queue: asyncio.Queue[tuple[Decision, dict[str, int | datetime]]] = asyncio.Queue(
            maxsize=SHADOW_QUEUE_CAPACITY
        )
        self.worker: asyncio.Task[None] | None = None
        self.monitor: asyncio.Task[None] | None = None
        self.download_tasks: dict[str, asyncio.Task[None]] = {}
        self.downloads: dict[str, dict[str, Any]] = {}
        self.maintenance_paused = False
        self.installed_models: list[dict[str, Any]] = []
        self.last_models_refresh: datetime | None = None
        self.runtime_status: dict[str, Any] = {
            "reachable": False,
            "version": None,
            "loaded_model_count": 0,
            "loaded_model_bytes": 0,
            "loaded_vram_bytes": 0,
            "compute": "unavailable",
        }
        self.qualification_cache: tuple[str, datetime, dict[str, Any]] | None = None
        self.last_qualification_result: dict[str, Any] | None = None
        self.current_recent_assessments: list[AiCriticAssessment] = []
        self.shadow_queue_drops = 0
        self.queued_mints: set[str] = set()
        self.pending_outcomes: dict[str, list[AiCriticAssessment]] = {}
        for assessment in database.unresolved_ai_assessments(5_000):
            self.pending_outcomes.setdefault(assessment.mint, []).append(assessment)

    async def start(self) -> None:
        try:
            await asyncio.wait_for(self.refresh_models(), timeout=6)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            # The optional AI service must never hold up API/market startup.
            self.last_models_refresh = datetime.now(UTC)
        except Exception as exc:
            # A malformed or future Ollama response is still an optional-provider failure. The
            # deterministic paper engine must start and the monitor can recover later.
            logger.warning("Optional Ollama startup probe failed: %s", redact_secrets(exc))
            self.last_models_refresh = datetime.now(UTC)
            self.runtime_status["reachable"] = False
            self.runtime_status["compute"] = "unavailable"
        if self.mode == AiDecisionMode.GUARDED:
            qualification = await asyncio.to_thread(self.qualification)
            if not qualification["qualified"]:
                self.mode = AiDecisionMode.SHADOW
                self.database.set_setting("ai_decision_mode", self.mode.value)
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._worker_loop(), name="ai-shadow-critic")
        if self.monitor is None or self.monitor.done():
            self.monitor = asyncio.create_task(self._monitor_loop(), name="ollama-monitor")

    async def stop(self) -> None:
        tasks = [
            task for task in [self.worker, self.monitor, *self.download_tasks.values()] if task
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.worker = None
        self.monitor = None
        self.download_tasks.clear()

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            if self.maintenance_paused:
                continue
            try:
                await self.refresh_models()
                # qualification() is cache-fast when nothing changed, but also notices a new risk,
                # fee, model, season, or prompt fingerprint. Keep scans off the market worker and
                # off interactive dashboard requests.
                await asyncio.to_thread(self.qualification)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Provider methods are deliberately fallback-safe. This final boundary ensures a
                # future provider regression still cannot terminate the optional monitor task.
                logger.warning("Optional Ollama monitor failed: %s", redact_secrets(exc))
                continue

    def set_mode(self, mode: AiDecisionMode) -> None:
        if mode == AiDecisionMode.GUARDED and not self.qualification()["qualified"]:
            raise ValueError(
                "AI Guarded mode stays locked until the selected model proves a positive, "
                "timely fee-inclusive veto benefit in Shadow mode"
            )
        self.mode = mode
        self.database.set_setting("ai_decision_mode", mode.value)
        if mode != AiDecisionMode.SHADOW:
            self._discard_queued_shadow()

    def has_pending_outcome(self, mint: str) -> bool:
        """Return whether a saved Shadow assessment still needs this mint's market data."""

        return bool(self.pending_outcomes.get(mint))

    def selected_model_provenance(self) -> tuple[str, str]:
        """Return the exact optional model identity used by durable advisory artifacts."""

        selected = self._installed_by_name(self.http.ollama_model)
        return self.http.ollama_model, str(selected.get("digest") or "") if selected else ""

    def enqueue_shadow(self, decision: Decision, state: TokenState) -> bool:
        if (
            self.maintenance_paused
            or self.mode != AiDecisionMode.SHADOW
            or decision.action != DecisionAction.ENTER
        ):
            return False
        # One unresolved five-minute outcome per token is enough to measure the critic. Repeated
        # snapshots of the same token are highly correlated, waste CPU, and can otherwise fill the
        # local model's queue without adding useful qualification evidence.
        if decision.mint in self.queued_mints or self.has_pending_outcome(decision.mint):
            return False
        outcome = self._prepare_outcome(decision, state)
        if outcome is None:
            return False
        try:
            self.queued_mints.add(decision.mint)
            self.queue.put_nowait((decision, outcome))
            return True
        except asyncio.QueueFull:
            self.queued_mints.discard(decision.mint)
            self.shadow_queue_drops += 1
            return False

    async def assess_guarded(self, decision: Decision, state: TokenState) -> Decision:
        if (
            self.maintenance_paused
            or self.mode != AiDecisionMode.GUARDED
            or decision.action != DecisionAction.ENTER
        ):
            return decision
        qualification = self.qualification()
        if not qualification["qualified"]:
            self.mode = AiDecisionMode.SHADOW
            self.database.set_setting("ai_decision_mode", self.mode.value)
            return decision
        outcome = self._prepare_outcome(decision, state)
        if outcome is None:
            return decision
        assessment = await self._assess(
            decision,
            outcome,
            applied=True,
            timeout_seconds=2.5,
        )
        if assessment is None:
            return decision
        self.database.save_ai_assessment(assessment)
        self._remember_current_assessment(assessment)
        self.qualification_cache = None
        self._track_pending(assessment)
        if (
            assessment.valid
            and assessment.verdict == AiCriticVerdict.VETO
            and assessment.confidence == "high"
        ):
            return decision.model_copy(
                update={
                    "action": DecisionAction.PASS,
                    "blockers": [*decision.blockers, "qualified_ai_critic_veto"],
                    "reasons": [
                        *decision.reasons,
                        "The qualified local AI critic preserved cash using cited saved evidence",
                    ],
                    "model_version": f"{decision.model_version}+{PROMPT_VERSION}",
                }
            )
        return decision

    async def _worker_loop(self) -> None:
        while True:
            decision, outcome = await self.queue.get()
            try:
                if self.maintenance_paused:
                    self.shadow_queue_drops += 1
                    continue
                if (
                    datetime.now(UTC) - decision.created_at
                ).total_seconds() > MAX_SHADOW_QUEUE_AGE_SECONDS:
                    # Do not spend scarce local CPU evaluating an old burst after newer market
                    # opportunities have arrived. No assessment was saved, so a fresh checkpoint
                    # for this mint may be evaluated later.
                    self.shadow_queue_drops += 1
                    continue
                try:
                    assessment = await self._assess(
                        decision,
                        outcome,
                        applied=False,
                        timeout_seconds=28,
                    )
                    if assessment is not None:
                        self.database.save_ai_assessment(assessment)
                        self._remember_current_assessment(assessment)
                        self.qualification_cache = None
                        self._track_pending(assessment)
                        await asyncio.to_thread(
                            self.database.resolve_incidents,
                            "ai_shadow_worker",
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await asyncio.to_thread(
                        self.database.record_incident,
                        scope="ai_shadow_worker",
                        severity="warning",
                        title="Local AI Shadow assessment failed",
                        detail=redact_secrets(f"{type(exc).__name__}: {exc}")[:500],
                        metadata={"decision_id": decision.decision_id},
                    )
            finally:
                self.queued_mints.discard(decision.mint)
                self.queue.task_done()

    async def _assess(
        self,
        decision: Decision,
        outcome: dict[str, int | datetime],
        *,
        applied: bool,
        timeout_seconds: float,
    ) -> AiCriticAssessment | None:
        assessment_mode = self.mode
        model = await self._selected_model()
        if model is None:
            return None
        digest = str(model.get("digest") or "")
        model_name = self.http.ollama_model
        evidence = critic_evidence_payload(decision)
        allowed_refs = set(evidence)
        input_payload = {"evidence": evidence}
        encoded = json.dumps(input_payload, separators=(",", ":"), sort_keys=True)
        input_hash = hashlib.sha256(encoded.encode()).hexdigest()
        prompt = _critic_prompt(encoded)
        schema = _critic_schema(allowed_refs)
        result = await self.http.ollama_structured(
            prompt=prompt,
            schema=schema,
            timeout_seconds=timeout_seconds,
            model=model_name,
        )
        assessment_id = hashlib.sha256(
            f"{decision.decision_id}:{digest}:{PROMPT_VERSION}".encode()
        ).hexdigest()
        common: dict[str, Any] = {
            "assessment_id": assessment_id,
            "decision_id": decision.decision_id,
            "mint": decision.mint,
            "symbol": decision.symbol,
            "snapshot_at": decision.feature_snapshot.computed_at,
            "mode": assessment_mode,
            "applied": applied,
            "model_name": model_name,
            "model_digest": digest,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "input_sha256": input_hash,
            "input_payload": input_payload,
            "baseline_action": decision.action,
            "season_id": decision.season_id,
            "season_profile_fingerprint": decision.season_profile_fingerprint,
            "configuration_fingerprint": decision.configuration_fingerprint,
            "token_units": outcome["token_units"],
            "entry_cost_lamports": outcome["entry_cost_lamports"],
            "fee_bps": outcome["fee_bps"],
            "outcome_due_at": outcome["outcome_due_at"],
        }
        if result is None:
            return AiCriticAssessment(
                **common,
                latency_ms=max(0, int(timeout_seconds * 1_000)),
                valid=False,
                invalid_reason="ollama_unavailable_or_timed_out",
            )
        raw, latency_ms = result
        try:
            payload = _CriticPayload.model_validate_json(raw)
            if not set(payload.evidence_refs).issubset(allowed_refs):
                raise ValueError("response cited evidence that was not supplied")
            if not set(payload.risk_flags).issubset(RISK_FLAGS):
                raise ValueError("response used an unsupported risk flag")
            if not payload.evidence_refs and payload.verdict != "insufficient_evidence":
                raise ValueError("support and veto require cited evidence")
        except (ValidationError, ValueError) as exc:
            return AiCriticAssessment(
                **common,
                latency_ms=latency_ms,
                valid=False,
                invalid_reason=str(exc)[:300],
            )
        return AiCriticAssessment(
            **common,
            latency_ms=latency_ms,
            valid=True,
            verdict=AiCriticVerdict(payload.verdict),
            confidence=payload.confidence,
            evidence_refs=payload.evidence_refs,
            risk_flags=payload.risk_flags,
            summary=_critic_summary(payload, evidence),
        )

    def observe_market(self, state: TokenState, now: datetime) -> int:
        assessments = list(self.pending_outcomes.get(state.mint, []))
        changed = 0
        for assessment in assessments:
            if assessment.outcome_due_at is None or now < assessment.outcome_due_at:
                continue
            if now > assessment.outcome_due_at + timedelta(seconds=90):
                updated = assessment.model_copy(
                    update={
                        "outcome_missing_reason": "no_fresh_trade_near_horizon",
                        "resolved_at": now,
                    }
                )
            elif (
                assessment.token_units is None
                or assessment.entry_cost_lamports is None
                or assessment.fee_bps is None
            ):
                updated = assessment.model_copy(
                    update={
                        "outcome_missing_reason": "legacy_outcome_seed_missing",
                        "resolved_at": now,
                    }
                )
            else:
                try:
                    exit_quote = quote_sell(
                        virtual_token_reserves=state.virtual_token_reserves,
                        virtual_sol_reserves=state.virtual_quote_reserves,
                        token_units=assessment.token_units,
                        fee_bps=state.fee_bps or assessment.fee_bps,
                        network_fee_lamports=(
                            self.settings.network_fee_lamports + self.settings.priority_fee_lamports
                        ),
                    )
                    outcome_return = (
                        exit_quote.wallet_sol_lamports - assessment.entry_cost_lamports
                    ) / assessment.entry_cost_lamports
                    outcome_return = max(-1.0, min(10.0, outcome_return))
                    uplift = None
                    if assessment.valid and assessment.verdict is not None:
                        uplift = (
                            -outcome_return
                            if assessment.verdict == AiCriticVerdict.VETO
                            and assessment.confidence == "high"
                            else 0.0
                        )
                    updated = assessment.model_copy(
                        update={
                            "outcome_net_return": outcome_return,
                            "counterfactual_uplift": uplift,
                            "resolved_at": now,
                        }
                    )
                except ValueError:
                    updated = assessment.model_copy(
                        update={
                            "outcome_missing_reason": "executable_exit_quote_unavailable",
                            "resolved_at": now,
                        }
                    )
            self.database.save_ai_assessment(updated)
            self.qualification_cache = None
            self._untrack_pending(assessment)
            changed += 1
        return changed

    def expire_outcomes(self, now: datetime) -> int:
        changed = 0
        for assessments in list(self.pending_outcomes.values()):
            for assessment in list(assessments):
                if (
                    assessment.outcome_due_at is None
                    or now <= assessment.outcome_due_at + timedelta(seconds=90)
                ):
                    continue
                updated = assessment.model_copy(
                    update={
                        "outcome_missing_reason": "no_fresh_trade_near_horizon",
                        "resolved_at": now,
                    }
                )
                self.database.save_ai_assessment(updated)
                self.qualification_cache = None
                self._untrack_pending(assessment)
                changed += 1
        return changed

    def _prepare_outcome(
        self,
        decision: Decision,
        state: TokenState,
    ) -> dict[str, int | datetime] | None:
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
            return None
        return {
            "token_units": entry.token_units,
            "entry_cost_lamports": entry.wallet_sol_lamports,
            "fee_bps": fee_bps,
            "outcome_due_at": decision.created_at + timedelta(seconds=PRIMARY_OUTCOME_SECONDS),
        }

    def _track_pending(self, assessment: AiCriticAssessment) -> None:
        if assessment.resolved_at is None and assessment.outcome_due_at is not None:
            items = self.pending_outcomes.setdefault(assessment.mint, [])
            if all(item.assessment_id != assessment.assessment_id for item in items):
                items.append(assessment)

    def _untrack_pending(self, assessment: AiCriticAssessment) -> None:
        items = self.pending_outcomes.get(assessment.mint, [])
        remaining = [item for item in items if item.assessment_id != assessment.assessment_id]
        if remaining:
            self.pending_outcomes[assessment.mint] = remaining
        else:
            self.pending_outcomes.pop(assessment.mint, None)

    def qualification(self) -> dict[str, Any]:
        curated_model = self.http.ollama_model in {str(item["name"]) for item in MODEL_CATALOG}
        selected = self._installed_by_name(self.http.ollama_model)
        digest = str(selected.get("digest") or "") if selected else ""
        current_configuration = self.configuration_fingerprint()
        cache_key = (
            f"{self.http.ollama_model}:{digest}:{PROMPT_VERSION}:"
            f"{SCHEMA_VERSION}:{current_configuration}"
        )
        now = datetime.now(UTC)
        if (
            self.qualification_cache is not None
            and self.qualification_cache[0] == cache_key
            and (now - self.qualification_cache[1]).total_seconds() < 30
        ):
            return dict(self.qualification_cache[2])
        matching = [
            item
            for item in self.database.list_ai_assessments(5_000)
            if item.model_name == self.http.ollama_model
            and item.model_digest == digest
            and item.prompt_version == PROMPT_VERSION
            and item.schema_version == SCHEMA_VERSION
            and item.configuration_fingerprint == current_configuration
        ]
        self.current_recent_assessments = matching[:20]
        resolved = [item for item in matching if item.resolved_at is not None]
        valid = [item for item in matching if item.valid]
        measurable = [item for item in resolved if item.counterfactual_uplift is not None]
        uplifts = [
            item.counterfactual_uplift
            for item in measurable
            if item.counterfactual_uplift is not None
        ]
        vetoes = [
            item
            for item in measurable
            if item.verdict == AiCriticVerdict.VETO and item.confidence == "high"
        ]
        mean_uplift = fmean(uplifts) if uplifts else None
        standard_error = None
        lower_bound = None
        if len(uplifts) >= 2 and mean_uplift is not None:
            variance = sum((value - mean_uplift) ** 2 for value in uplifts) / (len(uplifts) - 1)
            standard_error = math.sqrt(variance / len(uplifts))
            lower_bound = mean_uplift - QUALIFICATION_Z_SCORE * standard_error
        latencies = sorted(item.latency_ms for item in valid)
        p95_latency = (
            latencies[min(len(latencies) - 1, math.ceil(len(latencies) * 0.95) - 1)]
            if latencies
            else None
        )
        valid_fraction = len(valid) / len(matching) if matching else 0.0
        qualified = bool(
            curated_model
            and len(measurable) >= MINIMUM_RESOLVED_ASSESSMENTS
            and len(vetoes) >= MINIMUM_VETO_OUTCOMES
            and valid_fraction >= MINIMUM_VALID_FRACTION
            and lower_bound is not None
            and lower_bound > 0
            and p95_latency is not None
            and p95_latency <= MAX_GUARDED_P95_LATENCY_MS
        )
        gates = _ai_qualification_gates(
            curated_model=curated_model,
            resolved=len(measurable),
            vetoes=len(vetoes),
            valid_fraction=valid_fraction,
            uplift_lower_bound=lower_bound,
            p95_latency_ms=p95_latency,
        )
        result = {
            "qualified": qualified,
            "curated_model": curated_model,
            "model_digest": digest or None,
            "configuration_fingerprint": current_configuration,
            "assessments": len(matching),
            "resolved": len(measurable),
            "minimum_resolved": MINIMUM_RESOLVED_ASSESSMENTS,
            "veto_outcomes": len(vetoes),
            "minimum_veto_outcomes": MINIMUM_VETO_OUTCOMES,
            "valid_fraction": valid_fraction,
            "minimum_valid_fraction": MINIMUM_VALID_FRACTION,
            "mean_counterfactual_uplift": mean_uplift,
            "uplift_lower_bound": lower_bound,
            "p95_latency_ms": p95_latency,
            "maximum_p95_latency_ms": MAX_GUARDED_P95_LATENCY_MS,
            "gates": gates,
            "passed": sum(gate["state"] == "passed" for gate in gates),
            "total": len(gates),
        }
        self.qualification_cache = (cache_key, now, result)
        self.last_qualification_result = dict(result)
        return dict(result)

    def qualification_snapshot(self) -> dict[str, Any]:
        """Return the last completed audit without making an interactive view perform the scan."""

        current_configuration = self.configuration_fingerprint()
        if (
            self.last_qualification_result is not None
            and self.last_qualification_result.get("configuration_fingerprint")
            == current_configuration
        ):
            return dict(self.last_qualification_result)
        curated_model = self.http.ollama_model in {str(item["name"]) for item in MODEL_CATALOG}
        gates = _ai_qualification_gates(
            curated_model=curated_model,
            resolved=0,
            vetoes=0,
            valid_fraction=0.0,
            uplift_lower_bound=None,
            p95_latency_ms=None,
        )
        return {
            "qualified": False,
            "curated_model": curated_model,
            "model_digest": None,
            "configuration_fingerprint": current_configuration,
            "assessments": 0,
            "resolved": 0,
            "minimum_resolved": MINIMUM_RESOLVED_ASSESSMENTS,
            "veto_outcomes": 0,
            "minimum_veto_outcomes": MINIMUM_VETO_OUTCOMES,
            "valid_fraction": 0.0,
            "minimum_valid_fraction": MINIMUM_VALID_FRACTION,
            "mean_counterfactual_uplift": None,
            "uplift_lower_bound": None,
            "p95_latency_ms": None,
            "maximum_p95_latency_ms": MAX_GUARDED_P95_LATENCY_MS,
            "gates": gates,
            "passed": sum(gate["state"] == "passed" for gate in gates),
            "total": len(gates),
        }

    async def refresh_models(self) -> list[dict[str, Any]]:
        previous_models = {
            (str(item.get("name") or ""), str(item.get("digest") or ""))
            for item in self.installed_models
        }
        runtime, models = await asyncio.gather(
            self.http.ollama_runtime_status(),
            self.http.ollama_models(),
        )
        self.runtime_status = runtime
        self.installed_models = models
        self.last_models_refresh = datetime.now(UTC)
        current_models = {
            (str(item.get("name") or ""), str(item.get("digest") or "")) for item in models
        }
        if current_models != previous_models:
            self.qualification_cache = None
            self.last_qualification_result = None
            self.current_recent_assessments = []
        if self.mode == AiDecisionMode.GUARDED and not self.qualification()["qualified"]:
            self.mode = AiDecisionMode.SHADOW
            self.database.set_setting("ai_decision_mode", self.mode.value)
        return self.installed_models

    async def _selected_model(self) -> dict[str, Any] | None:
        if (
            self.last_models_refresh is None
            or (datetime.now(UTC) - self.last_models_refresh).total_seconds() > 60
        ):
            await self.refresh_models()
        return self._installed_by_name(self.http.ollama_model)

    def _installed_by_name(self, name: str) -> dict[str, Any] | None:
        aliases = {name, f"{name}:latest" if ":" not in name else name}
        return next(
            (
                item
                for item in self.installed_models
                if str(item.get("name") or item.get("model") or "") in aliases
            ),
            None,
        )

    def start_download(self, model: str) -> dict[str, Any]:
        if self.maintenance_paused:
            raise ValueError("finish or cancel upgrade preparation before downloading a model")
        if model not in {str(item["name"]) for item in MODEL_CATALOG}:
            raise ValueError("only curated local models can be downloaded from the web UI")
        running = self.download_tasks.get(model)
        if running is not None and not running.done():
            return self.downloads[model]
        if any(task is not None and not task.done() for task in self.download_tasks.values()):
            raise ValueError("wait for the current local model download to finish")
        job = {
            "model": model,
            "status": "queued",
            "completed_bytes": 0,
            "total_bytes": next(
                int(item["download_bytes"]) for item in MODEL_CATALOG if item["name"] == model
            ),
            "progress_fraction": 0.0,
            "message": "Waiting for Ollama",
            "error": None,
        }
        self.downloads[model] = job
        self.download_tasks[model] = asyncio.create_task(
            self._download_model(model), name=f"ollama-pull:{model}"
        )
        return job

    async def pause_for_maintenance(self) -> int:
        """Stop optional queued work without changing the configured AI mode or model."""

        self.maintenance_paused = True
        self._discard_queued_shadow()
        active = [
            (model, task)
            for model, task in self.download_tasks.items()
            if task is not None and not task.done()
        ]
        for model, task in active:
            task.cancel()
            job = self.downloads.get(model)
            if job is not None:
                job.update(
                    {
                        "status": "error",
                        "message": "Paused safely for an app update",
                        "error": "Restart this download after the update.",
                    }
                )
        if active:
            await asyncio.gather(*(task for _, task in active), return_exceptions=True)
        return len(active)

    def resume_after_maintenance(self) -> None:
        self.maintenance_paused = False

    async def _download_model(self, model: str) -> None:
        job = self.downloads[model]
        job["status"] = "downloading"

        def progress(item: dict[str, Any]) -> None:
            completed = int(item.get("completed") or job["completed_bytes"])
            total = int(item.get("total") or job["total_bytes"])
            job.update(
                {
                    "completed_bytes": completed,
                    "total_bytes": total,
                    "progress_fraction": min(1.0, completed / total) if total > 0 else 0.0,
                    "message": str(item.get("status") or "Downloading"),
                }
            )

        try:
            for attempt in range(1, MAX_MODEL_PULL_ATTEMPTS + 1):
                try:
                    await self.http.pull_ollama_model(model, progress)
                    break
                except ProviderError as exc:
                    if attempt >= MAX_MODEL_PULL_ATTEMPTS or not _retryable_pull_error(exc):
                        raise
                    delay_seconds = MODEL_PULL_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                    job.update(
                        {
                            "message": (
                                "Ollama registry unavailable; "
                                f"retrying in {delay_seconds}s ({attempt}/"
                                f"{MAX_MODEL_PULL_ATTEMPTS})"
                            ),
                            "error": None,
                        }
                    )
                    await asyncio.sleep(delay_seconds)
            await self.refresh_models()
            self.select_installed_model(model)
            await asyncio.to_thread(
                self.database.resolve_incidents,
                "ollama_model_download",
            )
            job.update(
                {
                    "status": "ready",
                    "progress_fraction": 1.0,
                    "completed_bytes": job["total_bytes"],
                    "message": "Downloaded and selected",
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = redact_secrets(exc)
            job.update({"status": "error", "error": error, "message": "Download failed"})
            await asyncio.to_thread(
                self.database.record_incident,
                scope="ollama_model_download",
                severity="warning",
                title="Local AI model download failed",
                detail=error,
                metadata={"model": model},
            )

    def select_installed_model(self, model: str) -> None:
        if self._installed_by_name(model) is None:
            raise ValueError("download this model before selecting it")
        self.select_model(model)
        self.qualification_cache = None
        self.last_qualification_result = None
        self.current_recent_assessments = []
        self._discard_queued_shadow()
        if self.mode == AiDecisionMode.GUARDED:
            self.mode = AiDecisionMode.SHADOW
            self.database.set_setting("ai_decision_mode", self.mode.value)

    async def remove_installed_model(self, model: str) -> dict[str, Any]:
        if model not in {str(item["name"]) for item in MODEL_CATALOG}:
            raise ValueError("only curated local models can be removed from the web UI")
        if any(task is not None and not task.done() for task in self.download_tasks.values()):
            raise ValueError("wait for the current local model download to finish")
        await self.refresh_models()
        if not self.runtime_status.get("reachable"):
            raise ValueError("the local AI runtime is unavailable")
        if bool(getattr(self.http, "ollama_generation_busy", False)):
            raise ValueError("wait for the current local AI assessment before removing a model")
        if self._installed_by_name(model) is None:
            if self.http.ollama_model == model:
                self.mode = AiDecisionMode.OFF
                self.database.set_setting("ai_decision_mode", self.mode.value)
            return self.status()
        await self.http.delete_ollama_model(model)
        await self.refresh_models()
        if self._installed_by_name(model) is not None:
            raise ProviderError("Ollama still reports the model as installed")
        if self.http.ollama_model == model:
            self.mode = AiDecisionMode.OFF
            self.database.set_setting("ai_decision_mode", self.mode.value)
        self.qualification_cache = None
        self.last_qualification_result = None
        self.current_recent_assessments = []
        return self.status()

    def status(
        self,
        *,
        recent_limit: int = 20,
        cached_qualification: bool = False,
    ) -> dict[str, Any]:
        memory_bytes = _available_system_memory_bytes()
        memory_gb = memory_bytes / 1024**3 if memory_bytes else None
        catalog = []
        for item in MODEL_CATALOG:
            installed = self._installed_by_name(str(item["name"]))
            catalog.append(
                {
                    **item,
                    "installed": installed is not None,
                    "installed_bytes": int(installed.get("size") or 0) if installed else None,
                    "digest": str(installed.get("digest") or "") if installed else None,
                    "fits_recommended_ram": _fits_recommended_memory(
                        memory_gb, int(item["recommended_ram_gb"])
                    ),
                }
            )
        try:
            ollama_host = (urlsplit(self.http.ollama_url).hostname or "").lower()
        except ValueError:
            ollama_host = ""
        bundled = ollama_host == "ollama"
        accelerator = self.settings.ollama_accelerator if bundled else "external"
        selected_installed = self._installed_by_name(self.http.ollama_model) is not None
        return {
            "mode": self.mode.value,
            "selected_model": self.http.ollama_model,
            "selected_model_installed": selected_installed,
            "ollama_available": bool(self.runtime_status.get("reachable")),
            "ollama_reachable": bool(self.runtime_status.get("reachable")),
            "ollama_version": self.runtime_status.get("version"),
            "deployment": "bundled" if bundled else "external",
            "configured_accelerator": accelerator,
            "runtime_compute": self.runtime_status.get("compute", "unknown"),
            "loaded_model_count": int(self.runtime_status.get("loaded_model_count") or 0),
            "loaded_model_bytes": int(self.runtime_status.get("loaded_model_bytes") or 0),
            "loaded_vram_bytes": int(self.runtime_status.get("loaded_vram_bytes") or 0),
            "last_checked_at": (
                self.last_models_refresh.isoformat() if self.last_models_refresh else None
            ),
            "system_memory_bytes": memory_bytes,
            "catalog": catalog,
            "downloads": list(self.downloads.values()),
            "queue_depth": self.queue.qsize(),
            "queue_capacity": self.queue.maxsize,
            "queue_drops": self.shadow_queue_drops,
            "inference_busy": bool(getattr(self.http, "ollama_generation_busy", False)),
            "qualification": (
                self.qualification_snapshot() if cached_qualification else self.qualification()
            ),
            "recent_assessments": [
                item.model_dump(mode="json")
                for item in self.current_recent_assessments[:recent_limit]
            ],
            "model_storage": "ollama_external",
            "model_storage_counts_toward_app_limit": False,
        }

    def _remember_current_assessment(self, assessment: AiCriticAssessment) -> None:
        selected = self._installed_by_name(self.http.ollama_model)
        digest = str(selected.get("digest") or "") if selected else ""
        if (
            assessment.model_name != self.http.ollama_model
            or assessment.model_digest != digest
            or assessment.prompt_version != PROMPT_VERSION
            or assessment.schema_version != SCHEMA_VERSION
            or assessment.configuration_fingerprint != self.configuration_fingerprint()
        ):
            return
        self.current_recent_assessments = [
            assessment,
            *(
                item
                for item in self.current_recent_assessments
                if item.assessment_id != assessment.assessment_id
            ),
        ][:20]

    def _discard_queued_shadow(self) -> None:
        """Discard work that no longer matches the user's selected AI mode or model."""

        while True:
            try:
                decision, _ = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self.queued_mints.discard(decision.mint)
            self.queue.task_done()


def _critic_prompt(input_json: str) -> str:
    return (
        "Risk-check this deterministic paper entry using only evidence. Return compact schema "
        "JSON. Cite exact evidence keys. Veto only for concrete risk; otherwise support or "
        "insufficient_evidence. Objects use v=value,q=quality,age_s=freshness. Evidence:"
        + input_json
    )


def _critic_schema(allowed_refs: set[str]) -> dict[str, Any]:
    """Constrain the decoder to real evidence and supported risk labels."""

    schema = _CriticPayload.model_json_schema()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        evidence_refs = properties.get("evidence_refs")
        risk_flags = properties.get("risk_flags")
        if isinstance(evidence_refs, dict):
            evidence_refs["items"] = {
                "type": "string",
                "enum": sorted(allowed_refs),
            }
        if isinstance(risk_flags, dict):
            risk_flags["items"] = {
                "type": "string",
                "enum": sorted(RISK_FLAGS),
            }
    return schema


def critic_evidence_payload(decision: Decision) -> dict[str, Any]:
    """Return a small, unit-preserving metric map for CPU-friendly structured inference."""

    evidence: dict[str, Any] = {
        "opportunity": _compact_number(decision.score.opportunity),
        "danger": _compact_number(decision.score.danger),
        "execution": _compact_number(decision.score.execution),
        "confidence": _compact_number(decision.score.confidence),
        "net_edge_index": _compact_number(decision.score.net_edge_index),
    }
    feature_names = {
        "trade_count_1m",
        "trade_count_5m",
        "buy_ratio_5m",
        "unique_wallets_5m",
        "wallet_volume_hhi",
        "repeated_amount_ratio",
        "same_slot_ratio",
        "creator_sells_5m",
        "curve_progress",
        "momentum_1m",
        "drawdown_5m",
        "virtual_quote_reserve_sol",
        "observed_fee_bps",
    }
    for name in sorted(feature_names):
        item = decision.feature_snapshot.values.get(name)
        if item is None:
            continue
        value = _compact_number(item.value)
        if item.quality >= 1 and item.freshness_seconds < 1 and not item.missing_reason:
            evidence[name] = value
            continue
        detail: dict[str, Any] = {"v": value}
        if item.quality < 1:
            detail["q"] = round(item.quality, 3)
        if item.freshness_seconds >= 1:
            detail["age_s"] = round(item.freshness_seconds, 1)
        if item.missing_reason:
            detail["missing"] = item.missing_reason[:80]
        evidence[name] = detail
    return evidence


def _compact_number(value: int | float | bool | str | None) -> int | float | bool | str | None:
    if isinstance(value, float):
        return round(value, 4)
    return value


_EVIDENCE_LABELS = {
    "opportunity": "opportunity",
    "danger": "danger",
    "execution": "execution quality",
    "confidence": "data confidence",
    "net_edge_index": "cost-aware edge",
    "trade_count_1m": "1-minute trades",
    "trade_count_5m": "5-minute trades",
    "buy_ratio_5m": "5-minute buy ratio",
    "unique_wallets_5m": "unique wallets",
    "wallet_volume_hhi": "wallet concentration",
    "repeated_amount_ratio": "repeated-size activity",
    "same_slot_ratio": "same-slot activity",
    "creator_sells_5m": "creator sells",
    "curve_progress": "curve progress",
    "momentum_1m": "1-minute momentum",
    "drawdown_5m": "5-minute drawdown",
    "virtual_quote_reserve_sol": "reserve depth",
    "observed_fee_bps": "observed fee",
}


def _critic_summary(payload: _CriticPayload, evidence: dict[str, Any]) -> str:
    references = [
        f"{_EVIDENCE_LABELS.get(ref, ref.replace('_', ' '))} {_format_evidence(ref, evidence[ref])}"
        for ref in payload.evidence_refs
        if ref in evidence
    ]
    cited = " and ".join(references)
    if payload.verdict == "veto":
        risks = ", ".join(flag.replace("_", " ") for flag in payload.risk_flags if flag != "none")
        detail = f" ({risks})" if risks else ""
        return f"Veto concern{detail}; cited {cited}." if cited else f"Veto concern{detail}."
    if payload.verdict == "support":
        return (
            f"Supports the baseline entry; cited {cited}."
            if cited
            else "Supports the baseline entry."
        )
    return (
        f"Evidence was insufficient for a reliable support or veto; checked {cited}."
        if cited
        else "Evidence was insufficient for a reliable support or veto."
    )


def _ai_qualification_gates(
    *,
    curated_model: bool,
    resolved: int,
    vetoes: int,
    valid_fraction: float,
    uplift_lower_bound: float | None,
    p95_latency_ms: int | None,
) -> list[dict[str, Any]]:
    """Expose the existing Shadow proof contract without granting future influence."""

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

    return [
        gate(
            "curated_model",
            "Reviewed model",
            curated_model,
            True,
            "=",
            curated_model,
            "boolean",
            "Only a reviewed local model and its installed digest can earn proof.",
        ),
        gate(
            "resolved_assessments",
            "Measured Shadow outcomes",
            resolved,
            MINIMUM_RESOLVED_ASSESSMENTS,
            ">=",
            resolved >= MINIMUM_RESOLVED_ASSESSMENTS,
            "count",
            "Assessments count only after their fee-inclusive outcome is known.",
        ),
        gate(
            "veto_outcomes",
            "High-confidence veto outcomes",
            vetoes,
            MINIMUM_VETO_OUTCOMES,
            ">=",
            vetoes >= MINIMUM_VETO_OUTCOMES,
            "count",
            "The model needs enough measurable veto calls to judge their value.",
        ),
        gate(
            "valid_fraction",
            "Valid assessment rate",
            valid_fraction,
            MINIMUM_VALID_FRACTION,
            ">=",
            valid_fraction >= MINIMUM_VALID_FRACTION,
            "fraction",
            "Malformed, unsupported, or timed-out assessments count against reliability.",
        ),
        gate(
            "uplift_floor",
            "Conservative Shadow value",
            uplift_lower_bound,
            0.0,
            ">",
            uplift_lower_bound is not None and uplift_lower_bound > 0,
            "fraction",
            "The confidence-adjusted counterfactual value must be positive.",
        ),
        gate(
            "latency",
            "Real-time latency proof",
            p95_latency_ms,
            MAX_GUARDED_P95_LATENCY_MS,
            "<=",
            p95_latency_ms is not None and p95_latency_ms <= MAX_GUARDED_P95_LATENCY_MS,
            "milliseconds",
            "This legacy real-time target is evidence only; future Coach design may differ.",
        ),
    ]


def _format_evidence(name: str, raw: Any) -> str:
    value = raw.get("v") if isinstance(raw, dict) else raw
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    if name in {
        "opportunity",
        "danger",
        "execution",
        "confidence",
        "buy_ratio_5m",
        "wallet_volume_hhi",
        "repeated_amount_ratio",
        "same_slot_ratio",
        "curve_progress",
        "momentum_1m",
        "drawdown_5m",
    }:
        return f"{value * 100:.1f}%"
    if name == "virtual_quote_reserve_sol":
        return f"{value:.3f} SOL"
    if name == "observed_fee_bps":
        return f"{value:g} bps"
    return f"{value:g}"


def decision_evidence_payload(decision: Decision) -> dict[str, dict[str, Any]]:
    """Return bounded decision-time evidence suitable for a small local model."""

    result: dict[str, dict[str, Any]] = {
        "score.opportunity": {"value": decision.score.opportunity},
        "score.danger": {"value": decision.score.danger},
        "score.execution": {"value": decision.score.execution},
        "score.confidence": {"value": decision.score.confidence},
        "score.net_edge_index": {
            "value": decision.score.net_edge_index,
        },
    }
    feature_names = {
        "trade_count_1m",
        "trade_count_5m",
        "buy_ratio_5m",
        "unique_wallets_5m",
        "wallet_volume_hhi",
        "repeated_amount_ratio",
        "same_slot_ratio",
        "creator_sells_5m",
        "curve_progress",
        "momentum_1m",
        "drawdown_5m",
        "virtual_quote_reserve_sol",
        "observed_fee_bps",
    }
    for name in sorted(feature_names):
        item = decision.feature_snapshot.values.get(name)
        if item is None:
            continue
        detail: dict[str, Any] = {"value": item.value}
        if item.unit != "fraction":
            detail["unit"] = item.unit
        # Keep exceptional provenance visible without serializing repetitive perfect-quality,
        # zero-age metadata for every feature. Raw source payloads are never passed to the model.
        if item.quality < 1:
            detail["quality"] = round(item.quality, 4)
        if item.freshness_seconds >= 1:
            detail["freshness_seconds"] = round(item.freshness_seconds, 1)
        if item.missing_reason:
            detail["missing_reason"] = item.missing_reason[:120]
        result[f"feature.{name}"] = detail
    return result


def _available_system_memory_bytes() -> int | None:
    totals: list[int] = []
    try:
        sysconf = vars(os)["sysconf"]  # Linux container API
        page_size = int(sysconf("SC_PAGE_SIZE"))
        pages = int(sysconf("SC_PHYS_PAGES"))
        totals.append(page_size * pages)
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        pass
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path, encoding="utf-8") as handle:
                raw = handle.read().strip()
            if raw != "max":
                value = int(raw)
                if 0 < value < 2**60:
                    totals.append(value)
        except (OSError, ValueError):
            continue
    return min(totals) if totals else None


def _fits_recommended_memory(memory_gb: float | None, recommended_gb: int) -> bool:
    """Treat the small cgroup/OS deduction from a nominal RAM tier as fitting it."""
    if memory_gb is None:
        return True
    return memory_gb >= recommended_gb * 0.95


def _retryable_pull_error(error: ProviderError) -> bool:
    detail = str(error).lower()
    return any(
        marker in detail
        for marker in (
            "timeout",
            "timed out",
            "temporar",
            "connection",
            "registry unavailable",
            "reset by peer",
            "unexpected eof",
            "status code 429",
            "status code 502",
            "status code 503",
            "status code 504",
        )
    )
