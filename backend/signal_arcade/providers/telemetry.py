"""Fixed-size, best-effort provider evidence. Never retain provider-controlled text."""

from __future__ import annotations

import time
import uuid
from contextlib import suppress
from typing import Any

from websockets.exceptions import ConnectionClosed

COUNTS = (
    "batch",
    "attempt",
    "response",
    "transport",
    "http",
    "rpc",
    "malformed",
    "cancelled",
    "cooldown",
    "quota",
    "context_changed",
    "subscription",
    "close",
    "other",
)
HTTP_CODES = (401, 403, 408, 413, 429, 500, 502, 503, 504)
OPERATIONS = ("accounts", "account", "transaction", "stream", "other")
METHODS = {
    "getMultipleAccounts": "accounts",
    "getAccountInfo": "account",
    "getTransaction": "transaction",
}
MAX_COUNT = 2**53 - 1


def safe_code(value: Any) -> int | None:
    return value if type(value) is int and -100_000 <= value <= 100_000 else None


class SubscriptionError(RuntimeError):
    def __init__(self, code: Any) -> None:
        self.code = safe_code(code)
        super().__init__("Subscription rejected")


def failure(exc: Exception) -> tuple[str, int | None]:
    status = safe_code(getattr(getattr(exc, "response", None), "status_code", None))
    if status is not None:
        return "http", status
    if isinstance(exc, SubscriptionError):
        return "subscription", exc.code
    code = safe_code(getattr(getattr(exc, "rcvd", None), "code", None))
    if code is not None or isinstance(exc, ConnectionClosed):
        return "close", code
    if isinstance(exc, (ValueError, TypeError)):
        return "malformed", None
    if isinstance(exc, (OSError, TimeoutError)):
        return "transport", None
    return "other", None


class ProviderTelemetry:
    def __init__(self, lane: str) -> None:
        if lane not in {"http", "ws"}:
            raise ValueError("Unknown provider lane")
        self.lane = lane
        self.scope = uuid.uuid4().hex
        self.counts = dict.fromkeys(COUNTS, 0)
        self.statuses = dict.fromkeys(HTTP_CODES, 0)
        self.last_attempt: dict[str, Any] | None = None
        self.last_response: dict[str, Any] | None = None
        self.last_failure: dict[str, Any] | None = None

    def record(
        self,
        category: str,
        *,
        role: str = "primary",
        operation: str = "other",
        code: Any = None,
        retry: float = 0.0,
    ) -> None:
        # Evidence must never turn a successful operation into a failed one.
        with suppress(Exception):
            self._record(category, role, operation, code, retry)

    def _record(self, category: str, role: str, operation: str, code: Any, retry: float) -> None:
        if category not in self.counts:
            category = "other"
        self.counts[category] = min(MAX_COUNT, self.counts[category] + 1)
        now = round(time.time(), 3)
        context = {
            "at": now,
            "role": role if role in {"primary", "fallback"} else "unknown",
            "operation": operation if operation in OPERATIONS else "other",
        }
        if category == "attempt":
            self.last_attempt = context
        elif category == "response":
            self.last_response = context
        elif category not in {"batch", "cooldown", "quota"}:
            self.last_failure = {
                **context,
                "category": category,
                "code": safe_code(code),
                "retry": round(retry, 3) if 0 <= retry <= 300 else 0.0,
            }
        if category == "http" and safe_code(code) in self.statuses:
            self.statuses[code] = min(MAX_COUNT, self.statuses[code] + 1)

    def event(self) -> dict[str, Any]:
        return {
            "kind": "provider_health",
            "version": 1,
            "lane": self.lane,
            "scope": self.scope,
            "at": round(time.time(), 3),
            "counts": dict(self.counts),
            "http_codes": {str(k): v for k, v in self.statuses.items()},
            "last_attempt": self.last_attempt,
            "last_response": self.last_response,
            "last_failure": self.last_failure,
        }


def record(telemetry: ProviderTelemetry, category: str, **fields: Any) -> None:
    """Also isolate an unavailable/replaced optional recorder from request semantics."""
    with suppress(Exception):
        telemetry.record(category, **fields)
