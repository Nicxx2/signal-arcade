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
from pathlib import Path
from typing import Any

from . import __version__
from .diagnostics_schema import PROOF_METRICS
from .diagnostics_store import BUDGET, COUNTERS, LAG_BOUNDS, MAX_INPUT, MAXIMA
from .diagnostics_worker import DiagnosticsWriter

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
    }
)


def identity(value: Any) -> str | None:
    return hashlib.sha256(str(value).encode()).hexdigest()[:24] if value is not None else None


def number(value: Any) -> float | int | bool | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return round(value, 6) if isinstance(value, float) else value
    return None


def artifact_summary(artifact: Any) -> dict[str, Any]:
    return {
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
        self, directory: Path, *, enabled: bool = True, can_write: Callable[[], bool] | None = None
    ) -> None:
        self.directory, self.enabled = directory.absolute(), enabled
        self.boot = uuid.uuid4().hex
        self.sequence = 0
        self.writer: DiagnosticsWriter | None = None
        self.can_write = can_write
        self.queue: deque[bytes] = deque(maxlen=4)
        self.events: deque[dict[str, Any]] = deque(maxlen=8)
        self.phases: dict[str, list[float]] = {}
        self.cursor = PipelineCursor()
        self.dropped = 0
        self.previous_at = time.time()
        self.previous_monotonic = time.monotonic()
        self.previous_context: dict[str, Any] | None = None
        self.previous_dropped = 0
        self.fingerprint: str | None = None
        self._status: dict[str, Any] = {"state": "starting" if enabled else "disabled"}

    async def start(self, frontend: Path | None = None) -> None:
        if not self.enabled or self.writer is not None:
            return
        try:
            self.fingerprint = await asyncio.to_thread(build_fingerprint, frontend)
            self.writer = DiagnosticsWriter(self.directory, self.can_write)
            self.writer.thread.start()
        except Exception:
            self.writer = None
            self._status = {"state": "unavailable", "error": "start_failed"}

    @property
    def total_dropped(self) -> int:
        return self.dropped + (self.writer.rejected if self.writer else 0)

    def observe_phase(self, name: str, started: float) -> None:
        if not self.enabled or name not in PHASES:
            return
        elapsed = max(0, time.monotonic() - started)
        phase = self.phases.setdefault(name, [0, 0.0, 0.0])
        phase[0] += 1
        phase[1] += elapsed
        phase[2] = max(phase[2], elapsed)

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Time a fixed operation on the event-loop thread; no I/O or payload retention."""
        started = time.monotonic()
        try:
            yield
        finally:
            self.observe_phase(name, started)

    def event(self, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            raw = json.dumps(value, separators=(",", ":"), allow_nan=False)
            if len(raw.encode()) > 2048:
                raise ValueError("event_too_large")
            value = json.loads(raw)
        except (ValueError, TypeError):
            self.dropped += 1
            return
        if len(self.events) == self.events.maxlen:
            self.dropped += 1
        self.events.append(value)

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
        flags = []
        if self.sequence == 0 or elapsed < 55:
            flags.append("partial_interval")
        if gap or elapsed > 90 or self.total_dropped > self.previous_dropped:
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
            "gauges": {**gauges, "diagnostics_dropped": self.total_dropped},
            "skills": skills,
            "events": list(self.events),
        }
        self.sequence += 1
        self.previous_at, self.previous_monotonic = at, mono
        self.previous_context = context
        self.previous_dropped = self.total_dropped
        self.events.clear()
        self.phases = {}
        try:
            raw = json.dumps(record, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            if len(raw) > MAX_INPUT:
                raise ValueError("record_too_large")
            if len(self.queue) == self.queue.maxlen:
                self.dropped += 1
            self.queue.append(raw)
        except (ValueError, TypeError):
            self.dropped += 1

    async def flush_one(self, *, allowed: bool) -> None:
        if self.writer is None:
            return
        if allowed:
            self.writer.allowed.set()
        else:
            self.writer.allowed.clear()
        if allowed and self.queue and self.writer.offer(self.queue[0]):
            self.queue.popleft()

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
