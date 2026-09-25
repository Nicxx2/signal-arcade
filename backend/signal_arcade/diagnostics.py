"""Best-effort, bounded diagnostics handoff outside the core executor and event lock."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from time import thread_time
from typing import Any

from . import __version__
from .diagnostics_optional import CUMULATIVE_REPORTS, optional_key
from .diagnostics_schema import PROOF_METRICS
from .diagnostics_store import BUDGET, COUNTERS, LAG_BOUNDS, MAX_INPUT, MAXIMA
from .diagnostics_worker import DiagnosticsWriter
from .intelligence.coverage import COVERAGE_BUCKETS, coverage_breakdown
from .runtime_evidence import SLOW_FIELDS, RuntimeEvidence
from .work_timing import WORK_FIELDS, WorkDetail

PHASES = frozenset(
    {
        "event_batch",
        "snapshot",
        "heartbeat",
        "training_prepare",
        "training_publish",
        "storage",
        "event_persist",
        "event_features",
        "event_learning",
        "event_ai",
        "event_broker",
        "event_candidate",
        "event_register",
        "event_decision_save",
        "season_boundary",
        "snapshot_cpu",
        "snapshot_wait",
        "heartbeat_cpu",
        "heartbeat_wait",
        "event_persist_cpu",
        "event_persist_wait",
        "event_learning_cpu",
        "event_learning_wait",
        "market_lock_wait",
        "snapshot_lock_wait",
        "heartbeat_lock_wait",
    }
)
PROTECTED_EVENTS = ("training", "training_error", "proof")
MAX_PUBLICATIONS_PENDING = 4
MAX_PUBLICATION_EVENTS = 7
OTHER_EVENT_KINDS = (
    "collection",
    "collection_expiry",
    "collection_selection",
    "reserve_validation",
    "reserve_layout",
    "diagnostic_loss",
    "heartbeat_work",
    "runtime_work",
    "work_detail",
    "collector_work",
    "slow_work",
    "provider_health",
    "retention_sample",
    "unknown",
)
_OPERATION: ContextVar[tuple[Any, str, dict[str, float]] | None] = ContextVar(
    "diagnostic_operation", default=None
)
Operation = tuple[Token[tuple[Any, str, dict[str, float]] | None], float]


def identity(value: Any) -> str | None:
    return hashlib.sha256(str(value).encode()).hexdigest()[:24] if value is not None else None


def number(value: Any) -> float | int | bool | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return round(value, 6) if isinstance(value, float) else value
    return None


def artifact_summary(artifact: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": identity(artifact.version),
        "skill": artifact.skill.value,
        "family": artifact.model_family.value,
        "qualified": artifact.qualified,
        "created_at": artifact.created_at.timestamp()
        if getattr(artifact, "created_at", None)
        else None,
        "counts": [artifact.sample_count, artifact.training_count, artifact.validation_count],
        "metrics": {
            key: number(artifact.metrics[key]) for key in PROOF_METRICS if key in artifact.metrics
        },
    }
    if "reference_availability_fraction" in artifact.metrics:
        # Named optional fields remain readable by older diagnostics schema-1 readers.
        summary["reference"] = {
            "coverage": number(artifact.metrics.get("reference_availability_fraction")),
            "uplift_lower": number(artifact.metrics.get("reference_uplift_lower_bound")),
        }
    coverage = coverage_breakdown(artifact.metrics, artifact.sample_count)
    if coverage is not None:
        # Fixed, versioned counts in the existing event; no extra queue slot or raw receipts.
        summary["coverage"] = [coverage[key] for key in ("schema", "resolved", *COVERAGE_BUCKETS)]
    parameters = getattr(artifact, "hyperparameters", {})
    if "coverage_policy_version" in parameters:
        summary["coverage_policy"] = {
            "percent": number(parameters.get("coverage_minimum_percent")),
            "revision": number(parameters.get("coverage_revision")),
            "fresh_validation": parameters.get("coverage_fresh_validation") is True,
        }
    return summary


def build_fingerprint(frontend: Path | None = None) -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    paths = [("backend/" + path.relative_to(root).as_posix(), path) for path in root.rglob("*.py")]
    paths += [
        ("backend/" + path.relative_to(root).as_posix(), path)
        for path in (root / "resources").rglob("*")
        if path.is_file()
    ]
    if frontend and frontend.is_dir():
        paths += [
            ("ui/" + path.relative_to(frontend).as_posix(), path)
            for path in frontend.rglob("*")
            if path.is_file() and path.suffix != ".map"
        ]
    for name, path in sorted(paths):
        digest.update(name.encode() + b"\0")
        with path.open("rb") as source:
            while chunk := source.read(65_536):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


class PipelineCursor:
    """Consume existing per-second buckets once, including increments to the final bucket."""

    def __init__(self) -> None:
        self.serial = 0
        self.last: dict[str, Any] = {}

    def take(self, buckets: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
        result: dict[str, Any] = {key: 0 for key in (*COUNTERS, *MAXIMA)}
        result.update(lag_histogram=[0] * 9, critical_histogram=[0] * 9)
        gap = bool(buckets and buckets[0]["serial"] > self.serial + 1)
        for item in buckets:
            if item["serial"] < self.serial:
                continue
            previous = self.last if item["serial"] == self.serial else {}
            for key in COUNTERS:
                result[key] += max(0, item.get(key, 0) - previous.get(key, 0))
            for key in ("lag_histogram", "critical_histogram"):
                values = item.get(key, [0] * 9)
                old = previous.get(key, [0] * 9)
                result[key] = [
                    a + max(0, b - c) for a, b, c in zip(result[key], values, old, strict=True)
                ]
            for key in MAXIMA:
                if item.get("processed", 0) > previous.get("processed", 0):
                    result[key] = max(result[key], item.get(key, 0))
        if buckets:
            self.last = dict(buckets[-1])
            self.last["lag_histogram"] = list(buckets[-1]["lag_histogram"])
            self.last["critical_histogram"] = list(buckets[-1].get("critical_histogram", [0] * 9))
            self.serial = buckets[-1]["serial"]
        return result, gap


class DiagnosticsRecorder:
    def __init__(
        self,
        directory: Path,
        *,
        enabled: bool = True,
        can_write: Callable[[], bool] | None = None,
        writer_blocked_reason: Callable[[], str | None] | None = None,
    ) -> None:
        self.directory, self.enabled = directory.absolute(), enabled
        self.boot = uuid.uuid4().hex
        self.sequence = 0
        self.writer: DiagnosticsWriter | None = None
        self.can_write = can_write
        self.writer_blocked_reason = writer_blocked_reason
        self.queue: deque[bytes] = deque(maxlen=4)
        self.events: deque[dict[str, Any]] = deque(maxlen=8)
        self._optional_collected: dict[tuple[str, str, tuple[int, ...]], tuple[str, float]] = {}
        self.optional_coalesced = 0
        self.ai_dispatch_since_boot = {"dispatch": 0, "not_due": 0}
        # Separate bounded publication groups absorb short bursts without enlarging a
        # writer message, changing cadence, or doing I/O on the publication boundary.
        self.publications: deque[tuple[float, list[dict[str, Any]]]] = deque()
        self._publication_serial = 0
        self.phases: dict[str, list[float]] = {}
        self.learning_waits_since_boot = {"dispatch": 0.0, "resume": 0.0}
        self.heartbeat_work_since_boot: dict[str, list[float]] = {}
        self.runtime_work_since_boot: dict[str, list[float]] = {}
        self.work_detail_since_boot: dict[str, WorkDetail] = {}
        self.runtime_evidence = RuntimeEvidence()
        self.cursor = PipelineCursor()
        self.dropped = 0
        self._loss_since_collection = False
        # Fixed dimensions, counted separately: reasons mix event/interval units;
        # categories describe only rejected/evicted input events. Compression omissions
        # belong to the store's per-interval omitted_events, never these counters.
        self.loss_reasons = dict.fromkeys(
            (
                "event_input",
                "event_capacity",
                "interval_input",
                "interval_queue",
                "collector_error",
                "reporting_error",
            ),
            0,
        )
        self.lost_event_categories = dict.fromkeys(("training", "proof", "storage", "other"), 0)
        # A fixed breakdown of "other", not extra losses or arbitrary event identifiers.
        self.lost_other_event_kinds = dict.fromkeys(OTHER_EVENT_KINDS, 0)
        self.collection_deferred = 0
        self.previous_at = time.time()
        self.previous_monotonic = time.monotonic()
        self.next_collection_monotonic = self.previous_monotonic + 60
        self.previous_context: dict[str, Any] | None = None
        self.previous_dropped = 0
        self.fingerprint: str | None = None
        self._status: dict[str, Any] = {"state": "starting" if enabled else "disabled"}

    async def start(self, frontend: Path | None = None) -> None:
        if not self.enabled or self.writer is not None:
            return
        try:
            self.fingerprint = await asyncio.to_thread(build_fingerprint, frontend)
            self.writer = DiagnosticsWriter(
                self.directory, self.can_write, self.writer_blocked_reason
            )
            self.writer.thread.start()
        except Exception:
            self.writer = None
            self._status = {"state": "unavailable", "error": "start_failed"}

    @property
    def total_dropped(self) -> int:
        return self.dropped + (self.writer.rejected if self.writer else 0)

    def collection_due(self, *, early: bool = False) -> bool:
        now = time.monotonic()
        return bool(
            self.enabled
            and now >= self.next_collection_monotonic - (5 if early else 0)
            and (not early or now - self.previous_monotonic >= 55)
        )

    def collection_attempted(self) -> None:
        # Early collection consumes the next nominal slot, not a new cadence. Late
        # collection starts a fresh minute rather than generating catch-up intervals.
        self.next_collection_monotonic = max(self.next_collection_monotonic, time.monotonic()) + 60

    def publication_needs_collection(self, incoming: int) -> bool:
        return bool(
            self.collection_due(early=True)
            # A long-stalled collector can have a large bucket backlog. Leave that
            # catch-up to its own loop, outside the publication's critical path.
            and time.monotonic() - self.previous_monotonic <= 90
            and (
                sum(item.get("kind") in PROTECTED_EVENTS for item in self.events)
                + self.pending_publication_events
                + incoming
                > 8
            )
            and len(self.queue) < 4
            and self.writer is not None
            and self.writer.thread.is_alive()
            and self.writer.status.get("state") == "recording"
        )

    def recording_failed(self, *, collection: bool) -> None:
        if self.enabled:
            self._record_loss("collector_error" if collection else "reporting_error")

    def observe_phase(self, name: str, started: float) -> None:
        if not self.enabled or name not in PHASES:
            return
        self.observe_duration(name, max(0, time.monotonic() - started))

    def observe_duration(self, name: str, elapsed: float) -> None:
        """Aggregate completed worker timings on the event loop, never from worker threads."""
        if not self.enabled or not math.isfinite(elapsed) or elapsed < 0:
            return
        self._observe_operation(name, elapsed)
        if name not in PHASES:
            return
        phase = self.phases.setdefault(name, [0, 0.0, 0.0])
        phase[0] += 1
        phase[1] += elapsed
        phase[2] = max(phase[2], elapsed)

    def begin_operation(self, lane: str) -> Operation | None:
        """Fixed task-local parts, no worker sampling or per-event I/O."""
        if not self.enabled or lane not in {"market", "snapshot", "enrichment"}:
            return None
        started = time.monotonic()
        return _OPERATION.set((self, lane, {})), started

    def _observe_operation(self, name: str, elapsed: float) -> None:
        operation = _OPERATION.get()
        if operation is not None and operation[0] is self and name in SLOW_FIELDS[operation[1]]:
            parts = operation[2]
            parts[name] = min(1e12, parts.get(name, 0.0) + elapsed)

    def finish_operation(self, operation: Operation | None, outcome: str) -> None:
        if operation is None:
            return
        token, started = operation
        current = _OPERATION.get()
        _OPERATION.reset(token)
        if current is not None and current[0] is self:
            # A reporting failure must not replace a market/snapshot result or exception.
            try:
                self.observe_slow_work(current[1], started, current[2], outcome)
            except Exception:
                self.recording_failed(collection=False)

    def observe_learning_waits(self, dispatch: float, resume: float) -> None:
        """Bounded cumulative seconds for collection events, outside the interval budget."""
        if not self.enabled:
            return
        for key, elapsed in (("dispatch", dispatch), ("resume", resume)):
            if math.isfinite(elapsed) and elapsed >= 0:
                self.learning_waits_since_boot[key] = min(
                    1e12, self.learning_waits_since_boot[key] + elapsed
                )

    def observe_ai_dispatch(self, due: bool) -> None:
        if self.enabled:
            key = "dispatch" if due else "not_due"
            self.ai_dispatch_since_boot[key] = min(2**53 - 1, self.ai_dispatch_since_boot[key] + 1)

    def observe_heartbeat_work(self, timing: dict[str, float]) -> None:
        """Called on the event loop after joining the heartbeat's worker."""
        if not self.enabled:
            return
        for name, elapsed in timing.items():
            if name not in {"positions", "cache", "expiry", "coach", "ai", "profile", "season"}:
                continue
            if not math.isfinite(elapsed) or elapsed < 0:
                continue
            values = self.heartbeat_work_since_boot.setdefault(name, [0, 0.0, 0.0])
            values[0] = min(2**53 - 1, values[0] + 1)
            values[1] = min(1e12, values[1] + elapsed)
            values[2] = max(values[2], min(1e12, elapsed))

    def observe_collection_result(self, result: str, reason: str | None = None) -> None:
        if self.enabled:
            try:
                self.runtime_evidence.collection_result(result, reason)
            except Exception:
                self.recording_failed(collection=False)

    def observe_collector_wake(self, seconds: float) -> None:
        if self.enabled:
            try:
                self.runtime_evidence.wake_delay(seconds)
            except Exception:
                self.recording_failed(collection=False)

    def observe_slow_work(
        self, lane: str, started: float, phases: dict[str, float], outcome: str
    ) -> None:
        if self.enabled:
            try:
                self.runtime_evidence.observe_slow(
                    lane,
                    started=started,
                    finished=time.monotonic(),
                    at=time.time(),
                    phases=phases,
                    outcome=outcome,
                )
            except Exception:
                self.recording_failed(collection=False)

    def observe_runtime_work(self, timing: dict[str, float]) -> None:
        """Optional cumulative detail; do not enlarge the interval phase payload."""
        if not self.enabled:
            return
        for name, elapsed in timing.items():
            if (
                name
                not in {
                    "snapshot_portfolio",
                    "snapshot_history",
                    "snapshot_tokens",
                    "snapshot_decisions",
                    "snapshot_learning",
                    "snapshot_advisory",
                    "snapshot_other",
                    "rpc_selection_wait",
                    "rpc_request",
                    "rpc_result_wait",
                    "rpc_storage_handoff",
                    "rpc_apply",
                }
                or not math.isfinite(elapsed)
                or elapsed < 0
            ):
                continue
            values = self.runtime_work_since_boot.setdefault(name, [0, 0.0, 0.0])
            values[0] = min(2**53 - 1, values[0] + 1)
            values[1] = min(1e12, values[1] + elapsed)
            values[2] = max(values[2], min(1e12, elapsed))
            self._observe_operation(name, elapsed)

    def observe_work_detail(self, lane: str, timing: WorkDetail) -> None:
        """Merge only after joining its owning worker; never enlarge interval phases."""
        if not self.enabled or lane not in WORK_FIELDS:
            return
        if lane == "broker":
            # Portfolio detail shares the joined broker worker, but has its own finite
            # optional stream so long-running counters still fit the durable byte cap.
            self.observe_work_detail(
                "equity",
                {name: values for name, values in timing.items() if name in WORK_FIELDS["equity"]},
            )
        if lane == "rpc" and any(name in WORK_FIELDS["governance"] for name in timing):
            self.observe_work_detail(
                "governance",
                {
                    name: values
                    for name, values in timing.items()
                    if name in WORK_FIELDS["governance"]
                },
            )
        for name, sample in timing.items():
            if (
                name not in WORK_FIELDS[lane]
                or len(sample) != 3
                or any(not math.isfinite(value) or value < 0 for value in sample)
            ):
                continue
            counts = self.work_detail_since_boot.setdefault(lane, {})
            values = counts.setdefault(name, [0, 0.0, 0.0])
            values[0] = min(2**53 - 1, values[0] + sample[0])
            values[1] = min(1e12, values[1] + sample[1])
            values[2] = min(1e12, max(values[2], sample[2]))
            self._observe_operation(name, sample[1])

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Time a fixed operation on the event-loop thread; no I/O or payload retention."""
        started = time.monotonic()
        cpu = thread_time() if self.enabled and name in {"event_features", "event_assess"} else None
        try:
            yield
        finally:
            if name == "event_assess":
                self.observe_duration(name, max(0.0, time.monotonic() - started))
            else:
                self.observe_phase(name, started)
            if cpu is not None:
                self.observe_duration(name + "_cpu", max(0.0, thread_time() - cpu))

    @property
    def pending_publication_events(self) -> int:
        return sum(len(events) for _, events in self.publications)

    def publication(self, events: list[dict[str, Any] | None]) -> None:
        """Keep up to four complete groups; overflow is explicit diagnostic loss."""
        if not self.enabled:
            return
        self._publication_serial += 1
        group = identity(f"{self.boot}:{self._publication_serial}")
        retained = []
        for index, event in enumerate(events[:MAX_PUBLICATION_EVENTS]):
            if event is None:
                # An unbuildable proof summary must leave an explicit hole in the
                # group's indices, without erasing its valid siblings.
                self._record_loss("event_input", {"kind": "proof"})
                continue
            if event.get("kind") not in PROTECTED_EVENTS:
                self._record_loss("event_input", event)
                continue
            value = self._detached_event({**event, "publication": [group, index, len(events)]})
            if value is not None:
                retained.append(value)
        for event in events[MAX_PUBLICATION_EVENTS:]:
            self._record_loss("event_capacity", event if event is not None else {"kind": "proof"})
        if not retained:
            return
        if len(self.publications) == MAX_PUBLICATIONS_PENDING:
            _, displaced = self.publications.popleft()
            for event in displaced:
                self._record_loss("event_capacity", event)
        self.publications.append((time.monotonic(), retained))

    def _detached_event(self, value: dict[str, Any]) -> dict[str, Any] | None:
        try:
            raw = json.dumps(value, separators=(",", ":"), allow_nan=False)
            if len(raw.encode()) > 2048:
                raise ValueError("event_too_large")
            result: dict[str, Any] = json.loads(raw)
            return result
        except (ValueError, TypeError, RecursionError):
            self._record_loss("event_input", value)
            return None

    def event(self, value: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        detached = self._detached_event(value)
        if detached is None:
            return False
        value = detached
        if len(self.events) == self.events.maxlen:
            # Optional detail must not displace directly submitted training/proof.
            # If protected events overflow this queue, retain the newest and count
            # the displaced record honestly; the main learning ledger is authoritative.
            victim = next(
                (
                    index
                    for index, item in enumerate(self.events)
                    if item.get("kind") not in PROTECTED_EVENTS
                ),
                None,
            )
            if victim is None and value.get("kind") not in PROTECTED_EVENTS:
                self._record_loss("event_capacity", value)
                return False
            victim = 0 if victim is None else victim
            self._record_loss("event_capacity", self.events[victim])
            del self.events[victim]
        self.events.append(value)
        return True

    def optional_events(self, events: list[dict[str, Any]]) -> None:
        """Fair bounded admission. Cadence starts at collection, never mere acceptance."""
        if not self.enabled:
            return
        now = time.monotonic()
        if not math.isfinite(now):
            return
        candidates = []
        for event in events:
            key = optional_key(event)
            if key is None:
                self._record_loss("event_input", event)
                continue
            last = self._optional_collected.get(key)
            collected = last[1] if last and last[0] == event["scope"] else -math.inf
            candidates.append((collected, key, event))
        # Stable order for never-collected streams; already served streams go last.
        for collected, key, event in sorted(candidates, key=lambda row: row[0]):
            queued = next(
                (i for i, item in enumerate(self.events) if optional_key(item) == key), None
            )
            if queued is not None:
                old = self.events[queued]
                # Preserve old-scope observations until collected, not relabelled as current.
                if old.get("scope") != event["scope"]:
                    continue
                replace = event["kind"] in CUMULATIVE_REPORTS or (
                    event["kind"] == "slow_work" and event.get("elapsed", 0) > old.get("elapsed", 0)
                )
                if replace and old != event:
                    detached = self._detached_event(event)
                    if detached is not None:
                        self.events[queued] = detached
                        self.optional_coalesced = min(2**53 - 1, self.optional_coalesced + 1)
                continue
            if now - collected < 300 or len(self.events) >= 8:
                continue
            detached = self._detached_event(event)
            if detached is not None:
                self.events.append(detached)

    def _take_events(self, at: float) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        # Whole groups keep a publication together. Leave at least one slot for
        # ordinary diagnostics; sustained overload still has finite retention.
        while self.publications and len(selected) + len(self.publications[0][1]) <= 7:
            _, group = self.publications.popleft()
            selected.extend({**event, "collected_at": at} for event in group)
        while self.events and len(selected) < 8:
            # Training errors retain priority over optional detail, even if a group
            # used seven slots. Unselected events remain bounded for the next pass.
            index = next(
                (i for i, event in enumerate(self.events) if event.get("kind") in PROTECTED_EVENTS),
                0,
            )
            event = self.events[index]
            selected.append(event)
            del self.events[index]
            key = optional_key(event)
            if key is not None:
                self._optional_collected[key] = (event["scope"], time.monotonic())
                self.runtime_evidence.collected(event)
        return selected

    def _record_loss(self, reason: str, event: dict[str, Any] | None = None) -> None:
        self._loss_since_collection = True
        self.dropped = min(2**53 - 1, self.dropped + 1)
        self.loss_reasons[reason] = min(2**53 - 1, self.loss_reasons[reason] + 1)
        if event is not None:
            kind = event.get("kind")
            category = "other"
            if kind == "training_error":
                category = "training"
            elif isinstance(kind, str) and kind in self.lost_event_categories:
                category = kind
            self.lost_event_categories[category] = min(
                2**53 - 1, self.lost_event_categories[category] + 1
            )
            if category == "other":
                detail = (
                    kind
                    if isinstance(kind, str) and kind in self.lost_other_event_kinds
                    else "unknown"
                )
                self.lost_other_event_kinds[detail] = min(
                    2**53 - 1, self.lost_other_event_kinds[detail] + 1
                )

    def loss_counts(self) -> dict[str, Any]:
        """Cumulative boot counters; event categories are a breakdown, not extra losses."""
        return {
            **self.loss_reasons,
            "event_categories": dict(self.lost_event_categories),
            "other_event_kinds": {
                kind: count for kind, count in self.lost_other_event_kinds.items() if count
            },
            "writer_intervals": self.writer.rejected if self.writer else 0,
        }

    def collect(
        self,
        *,
        pipeline: dict[str, Any],
        context: dict[str, Any],
        gauges: dict[str, Any],
        skills: list[dict[str, Any]],
        gap: bool = False,
    ) -> None:
        if not self.enabled:
            return
        at, mono = time.time(), time.monotonic()
        elapsed = mono - self.previous_monotonic
        # The writer increments its rejected count on another thread. Use one
        # watermark for flags, the saved gauge and the next comparison; otherwise
        # a rejection between reads can advance the watermark without recording a gap.
        dropped = self.total_dropped
        flags = []
        if self.sequence == 0 or elapsed < 55:
            flags.append("partial_interval")
        if gap or elapsed > 90 or self._loss_since_collection or dropped > self.previous_dropped:
            flags.append("recording_gap")
        if abs(at - self.previous_at - elapsed) > 5:
            flags.append("clock_jump")
        if int(at // 3600) != int(self.previous_at // 3600):
            flags.append("hour_boundary")
        if self.previous_context is not None and context != self.previous_context:
            flags.append("mixed_context")
        record = {
            "boot": self.boot,
            "seq": self.sequence,
            "start": self.previous_at,
            "end": at,
            "elapsed": round(min(86400, max(0, elapsed)), 6),
            "flags": flags,
            "context": context,
            "pipeline": pipeline,
            "phases": self.phases,
            "gauges": {
                **gauges,
                "diagnostics_dropped": dropped,
                "diagnostics_deferred": self.collection_deferred,
            },
            "skills": skills,
            "events": self._take_events(at),
        }
        self.sequence += 1
        self.previous_at, self.previous_monotonic = at, mono
        self.previous_context = context
        self.previous_dropped = dropped
        self._loss_since_collection = False
        self.phases = {}
        try:
            raw = json.dumps(record, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            if len(raw) > MAX_INPUT:
                raise ValueError("record_too_large")
            if len(self.queue) == self.queue.maxlen:
                self._record_loss("interval_queue")
            self.queue.append(raw)
        except (ValueError, TypeError, RecursionError):
            self._record_loss("interval_input")

    async def flush_one(self, *, allowed: bool) -> None:
        if self.writer is None:
            return
        if allowed:
            self.writer.allowed.set()
        else:
            self.writer.allowed.clear()
        if allowed and self.queue and self.writer.offer(self.queue[0]):
            self.queue.popleft()

    def _writer_wait_status(self) -> dict[str, Any] | None:
        if self.writer is None:
            return None
        try:
            return self.writer.wait_status()
        except Exception:
            self.recording_failed(collection=False)
            return None

    def writer_wait_event(self) -> dict[str, Any] | None:
        status = self._writer_wait_status()
        if status is None or not any(status["episodes_since_boot"].values()):
            return None
        return {
            "kind": "collector_work",
            "version": 1,
            "lane": "writer",
            "scope": self.boot,
            "at": time.time(),
            **status,
        }

    def status(self) -> dict[str, Any]:
        ack = self.writer.last_ack_monotonic if self.writer else None
        return {
            **self._status,
            **(self.writer.status if self.writer else {}),
            "enabled": self.enabled,
            "budget_bytes": BUDGET,
            "boot": self.boot,
            "build": self.fingerprint,
            "version": __version__,
            "ack_age_seconds": max(0, time.monotonic() - ack) if ack is not None else None,
            "queued": len(self.queue)
            + (self.writer.messages.qsize() + int(self.writer.busy) if self.writer else 0),
            "dropped": self.total_dropped,
            "loss_since_boot": self.loss_counts(),
            "collection_deferred": self.collection_deferred,
            "writer_wait": self._writer_wait_status(),
            "runtime_evidence": self.runtime_evidence.status(),
            "optional_coalesced": self.optional_coalesced,
            "ai_dispatch_since_boot": dict(self.ai_dispatch_since_boot),
            "publication_backlog": {
                "groups": len(self.publications),
                "events": self.pending_publication_events,
                "oldest_age_seconds": max(0, time.monotonic() - self.publications[0][0])
                if self.publications
                else 0,
                "capacity_groups": MAX_PUBLICATIONS_PENDING,
                "state": "pending_collection" if self.publications else "empty",
            },
            "minute_days": 30,
            "hour_days": 365,
            "event_days": 90,
            "lag_bounds_seconds": LAG_BOUNDS,
            "histogram_overflow": ">30 seconds",
            "gauges": "last sample, not hour averages",
        }

    async def stop(self) -> None:
        if self.writer is not None:
            self.writer.request_stop()
            if self.writer.thread.is_alive():
                await asyncio.to_thread(self.writer.thread.join, 2)
