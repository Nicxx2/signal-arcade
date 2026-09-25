"""Fixed-size observational facts, owned by the event loop after workers join."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .work_timing import WORK_FIELDS

ADMISSION_REASONS = ("maintenance", "storage", "queue", "lag", "invalid_lag", "training")
COLLECTION_RESULTS = ("attempt", "collected", "lock_timeout", "superseded", "stopped", "error")
SLOW_FIELDS = {
    "broker": tuple(sorted(WORK_FIELDS["broker"] | WORK_FIELDS["equity"])),
    "market": (
        "event_persist",
        "event_persist_cpu",
        "event_persist_wait",
        "market_lock_wait",
        "event_features",
        "event_features_cpu",
        "event_assess",
        "event_assess_cpu",
        "event_learning",
        "event_learning_cpu",
        "event_learning_wait",
        "event_ai",
        "event_ai_cpu",
        "event_ai_wait",
        "event_broker",
        "event_candidate",
        "event_candidate_cpu",
        "event_candidate_wait",
        "event_candidate_dispatch",
        "event_candidate_resume",
        "event_candidate_worker",
        "event_register",
        "event_decision_save",
        "broker_dispatch",
        "broker_resume",
        "decision_dispatch",
        "decision_resume",
        "decision_lock",
        "decision_commit",
    ),
    "snapshot": (
        "snapshot_lock_wait",
        "snapshot_cpu",
        "snapshot_wait",
        "snapshot_portfolio",
        "snapshot_history",
        "snapshot_tokens",
        "snapshot_decisions",
        "snapshot_learning",
        "snapshot_advisory",
        "snapshot_other",
    ),
    "storage": (
        "capacity_before_seconds",
        "capacity_before_dispatch",
        "capacity_before_worker",
        "capacity_before_cpu",
        "capacity_before_read",
        "capacity_before_resume",
        "history_seconds",
        "history_worker_seconds",
        "history_worker_cpu_seconds",
        "history_lock_wait_seconds",
        "history_query_seconds",
        "history_execute_seconds",
        "history_execute_cpu_seconds",
        "history_transaction_exit_seconds",
        "history_setup_seconds",
        "history_restore_seconds",
        "history_dispatch_resume_seconds",
        "retired_decisions_seconds",
        "budget_seconds",
        "optional_history_seconds",
        "optional_incidents_seconds",
        "optional_ai_assessments_seconds",
        "optional_lock_wait_seconds",
        "optional_query_seconds",
        "optional_dispatch_resume_seconds",
        "capacity_seconds",
        "capacity_dispatch",
        "capacity_worker",
        "capacity_cpu",
        "capacity_read",
        "capacity_resume",
    ),
    "capacity": (
        "stage",
        "dispatch",
        "worker",
        "cpu",
        "read",
        "resume",
        "lock_wait",
        "setup",
        "query",
        "restore",
        "admission_deferred",
        "lock_deferred",
        "setup_deferred",
        "sql_busy",
        "sql_interrupted",
    ),
    "heartbeat": ("positions", "cache", "expiry", "coach", "ai", "profile", "season"),
    "persist": (
        "persist_dispatch",
        "persist_worker",
        "persist_resume",
        "persist_serialize",
        "persist_lock",
        "persist_sql",
        "persist_transaction",
    ),
    "enrichment": (
        "enrichment_lock_wait",
        "enrichment_prepare",
        "enrichment_metadata",
        "enrichment_route",
        "enrichment_cpu",
        "enrichment_wait",
        "enrichment_dispatch",
        "enrichment_resume",
        "enrichment_worker",
    ),
}


def bounded(value: float) -> float:
    return round(min(1e12, value), 6)


class RuntimeEvidence:
    def __init__(self) -> None:
        self.collection = dict.fromkeys(COLLECTION_RESULTS, 0)
        self.before = dict.fromkeys(ADMISSION_REASONS, 0)
        self.after = dict.fromkeys(ADMISSION_REASONS, 0)
        self.writer = dict.fromkeys(ADMISSION_REASONS, 0)
        self.wake = [0.0, 0.0, 0.0]
        self.slow: dict[str, dict[str, Any]] = {}
        self.serial = 0

    def collection_result(self, result: str, reason: str | None = None) -> None:
        if reason is None:
            counts = self.collection
            key = result
        else:
            if result not in {"before", "after", "writer"}:
                return
            counts = {"before": self.before, "after": self.after, "writer": self.writer}[result]
            key = reason
        if key in counts:
            counts[key] = min(2**53 - 1, counts[key] + 1)

    def wake_delay(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            return
        self.wake[0] = min(2**53 - 1, self.wake[0] + 1)
        self.wake[1] = min(1e12, self.wake[1] + seconds)
        self.wake[2] = min(1e12, max(self.wake[2], seconds))

    def collector_event(self, boot: str, at: float) -> dict[str, Any] | None:
        if not self.collection["attempt"] and not any(self.writer.values()):
            return None
        return {
            "kind": "collector_work",
            "version": 1,
            "scope": boot,
            "at": at,
            "counts_since_boot": dict(self.collection),
            "before": dict(self.before),
            "after": dict(self.after),
            "writer": dict(self.writer),
            "wake_seconds": [bounded(value) for value in self.wake],
        }

    def observe_slow(
        self,
        lane: str,
        *,
        started: float,
        finished: float,
        at: float,
        phases: dict[str, float],
        outcome: str,
    ) -> None:
        if (
            lane not in SLOW_FIELDS
            or outcome not in {"complete", "yielded", "error", "cancelled"}
            or any(not math.isfinite(value) or value < 0 for value in (started, finished, at))
            or finished < started
        ):
            return
        elapsed = bounded(finished - started)
        old = self.slow.get(lane)
        if old is not None and old["elapsed"] >= elapsed:
            return
        self.serial = min(2**53 - 1, self.serial + 1)
        # Missing/unfinished phases remain absent rather than becoming false zeroes.
        self.slow[lane] = {
            "sample": self.serial,
            "at": bounded(at),
            "elapsed": elapsed,
            "monotonic": [bounded(started), bounded(finished)],
            "outcome": outcome,
            "phases": {
                key: bounded(phases[key])
                for key in SLOW_FIELDS[lane]
                if key in phases and math.isfinite(phases[key]) and phases[key] >= 0
            },
        }

    def slow_event(self, lane: str, boot: str) -> dict[str, Any] | None:
        value = self.slow.get(lane)
        if value is None:
            return None
        return {"kind": "slow_work", "version": 1, "scope": boot, "lane": lane, **deepcopy(value)}

    def collected(self, event: dict[str, Any]) -> None:
        """Release only the exact sample selected for an interval; still not durable."""
        lane = event.get("lane")
        if event.get("kind") != "slow_work" or not isinstance(lane, str):
            return
        current = self.slow.get(lane)
        if current is not None and current["sample"] == event.get("sample"):
            del self.slow[lane]

    def status(self) -> dict[str, Any]:
        return {
            "collection_since_boot": dict(self.collection),
            "before": dict(self.before),
            "after": dict(self.after),
            "writer": dict(self.writer),
            "wake_seconds": [bounded(value) for value in self.wake],
            "pending_slow_samples": deepcopy(self.slow),
            "sample_state": "pending_optional_handoff_not_durable",
        }
