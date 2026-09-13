"""Bounded, passive health of shared-account validation; never authorizes a quote."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any

from .reserve_refresh import ReserveRefreshRejected

_SOURCES = ("learning", "watchdog")
_VENUES = ("pump_curve", "pump_swap")
_ACCOUNTS = frozenset({"FeeConfig", "Global", "GlobalConfig"})
_REASONS = frozenset({"unsupported_account_layout", "unreviewed_account_extension"})
_MAX_COUNT = 2**63 - 1


def compact_validation_health(status: dict[str, Any]) -> list[int]:
    """Four seven-bit samples; encoding/order documented in DIAGNOSTICS_HISTORY.md.

    Counts and timestamps stay in the live API. This field belongs to a separate event,
    never the size-constrained core interval; it cannot consume another proof-event slot.
    """
    states = {"not_observed": 0, "verified": 1, "checking": 2, "blocked": 3}
    accounts = {None: 0, "FeeConfig": 1, "Global": 2, "GlobalConfig": 3}
    reasons = {None: 0, "unreviewed_account_extension": 1, "unsupported_account_layout": 2}
    return [
        int(row["active"]) * 64
        + states[row["state"]] * 16
        + accounts[row["account_type"]] * 4
        + reasons[row["reason"]]
        for row in status["components"]
    ]


@dataclass
class _Health:
    failed_batches: int = 0
    first_failure: float | None = None
    last_failure_at: float | None = None
    last_success_at: float | None = None
    reason: str | None = None
    account_type: str | None = None
    blocked: bool = False
    layout: dict[str, int | str] | None = None


class ValidationBatch:
    def __init__(self) -> None:
        self.samples: dict[str, tuple[str, str, dict[str, int | str] | None] | None] = {}

    def accepted(self, venue: str) -> None:
        if venue in _VENUES:
            self.samples.setdefault(venue, None)

    def rejected(self, venue: str, error: ReserveRefreshRejected) -> None:
        if venue in _VENUES and error.account_type in _ACCOUNTS and str(error) in _REASONS:
            # A mixed batch's shared-config failure wins regardless of route order.
            self.samples[venue] = (
                str(error),
                str(error.account_type),
                dict(error.layout) if error.layout is not None else None,
            )


class ReserveValidationHealth:
    def __init__(self) -> None:
        self._lock = Lock()
        self._health = {(source, venue): _Health() for source in _SOURCES for venue in _VENUES}

    @contextmanager
    def batch(self, source: str) -> Iterator[ValidationBatch]:
        batch = ValidationBatch()
        try:
            yield batch
        finally:
            self._record(source, batch)

    def _record(self, source: str, batch: ValidationBatch) -> None:
        if source not in _SOURCES or not batch.samples:
            return
        monotonic, at = time.monotonic(), time.time()
        with self._lock:
            for venue, failure in batch.samples.items():
                health = self._health[source, venue]
                if failure is None:
                    health.failed_batches = 0
                    health.first_failure = None
                    health.last_success_at = at
                    health.reason = health.account_type = None
                    health.blocked = False
                    health.layout = None
                else:
                    health.failed_batches = min(_MAX_COUNT, health.failed_batches + 1)
                    if health.first_failure is None:
                        health.first_failure = monotonic
                    health.last_failure_at = at
                    health.reason, health.account_type, health.layout = failure
                    # Count requests, not many routes sharing the same config in one request.
                    # A short transient or one busy batch must not raise a persistent warning.
                    health.blocked |= (
                        health.failed_batches >= 3 and monotonic - health.first_failure >= 30
                    )

    def status(self, *, learning: bool, watchdog: bool) -> dict[str, Any]:
        active = {"learning": learning, "watchdog": watchdog}
        with self._lock:
            components = [
                {
                    "source": source,
                    "venue": venue,
                    "active": active[source],
                    "state": (
                        "blocked"
                        if value.blocked
                        else "checking"
                        if value.failed_batches
                        else "verified"
                        if value.last_success_at is not None
                        else "not_observed"
                    ),
                    "failed_batches": value.failed_batches,
                    "reason": value.reason,
                    "account_type": value.account_type,
                    "last_failure_at": value.last_failure_at,
                    "last_success_at": value.last_success_at,
                    "layout": dict(value.layout) if value.layout is not None else None,
                }
                for (source, venue), value in self._health.items()
            ]
        return {
            "attention": any(row["active"] and row["state"] == "blocked" for row in components),
            "components": components,
        }
