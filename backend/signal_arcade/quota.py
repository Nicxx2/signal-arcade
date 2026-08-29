from __future__ import annotations

import asyncio
import calendar
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .database import Database


@dataclass(frozen=True, slots=True)
class ProviderPlan:
    name: str
    requests_per_minute: int
    monthly_limit: int | None = None
    reserve_fraction: float = 0.10
    billable: bool = False
    pace_monthly: bool = False


@dataclass(slots=True)
class _Bucket:
    plan: ProviderPlan
    tokens: float = field(init=False)
    updated: float = field(default_factory=time.monotonic)
    unavailable_until: float = 0.0

    def __post_init__(self) -> None:
        self.tokens = _bucket_capacity(self.plan)

    def refill(self, now: float, effective_rpm: float) -> None:
        elapsed = max(0.0, now - self.updated)
        rate = effective_rpm / 60.0
        capacity = _bucket_capacity(self.plan, effective_rpm)
        self.tokens = min(capacity, self.tokens + elapsed * rate)
        self.updated = now


class QuotaBroker:
    """Central request governor. It never permits billable use implicitly."""

    def __init__(
        self,
        database: Database,
        plans: list[ProviderPlan],
        *,
        allow_billable: bool = False,
    ) -> None:
        self.database = database
        self.allow_billable = allow_billable
        self._buckets = {plan.name: _Bucket(plan) for plan in plans}
        self._lock = asyncio.Lock()

    @staticmethod
    def _month_key(now: datetime | None = None) -> str:
        return (now or datetime.now(UTC)).strftime("%Y-%m")

    async def acquire(self, provider: str, *, critical: bool = False) -> bool:
        async with self._lock:
            bucket = self._buckets.get(provider)
            if bucket is None:
                return False
            if bucket.plan.billable and not self.allow_billable:
                return False
            month = self._month_key()
            usage = (await asyncio.to_thread(self.database.provider_usage, month)).get(provider, 0)
            if bucket.plan.monthly_limit is not None:
                reserve = int(bucket.plan.monthly_limit * bucket.plan.reserve_fraction)
                routine_limit = bucket.plan.monthly_limit - reserve
                limit = bucket.plan.monthly_limit if critical else routine_limit
                if usage >= limit:
                    return False
            now = time.monotonic()
            if now < bucket.unavailable_until:
                return False
            effective_rpm = _effective_requests_per_minute(bucket.plan, critical=critical)
            bucket.refill(now, effective_rpm)
            if bucket.tokens < 1:
                return False
            bucket.tokens -= 1
            await asyncio.to_thread(self.database.increment_provider_usage, provider, month)
            return True

    async def penalize(self, provider: str, retry_after_seconds: float) -> None:
        """Honor provider backoff without spending more calls on immediate retries."""
        async with self._lock:
            bucket = self._buckets.get(provider)
            if bucket is None:
                return
            delay = max(1.0, min(300.0, retry_after_seconds))
            bucket.tokens = 0.0
            bucket.updated = time.monotonic()
            bucket.unavailable_until = bucket.updated + delay

    async def reconfigure(self, plans: list[ProviderPlan], *, allow_billable: bool) -> None:
        async with self._lock:
            self.allow_billable = allow_billable
            previous = self._buckets
            self._buckets = {}
            for plan in plans:
                bucket = _Bucket(plan)
                old = previous.get(plan.name)
                if old is not None:
                    bucket.tokens = min(bucket.tokens, old.tokens)
                    bucket.unavailable_until = old.unavailable_until
                self._buckets[plan.name] = bucket

    async def wait(
        self,
        provider: str,
        *,
        critical: bool = False,
        timeout_seconds: float = 5,
    ) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if await self.acquire(provider, critical=critical):
                return True
            await asyncio.sleep(0.1)
        return False

    def snapshot(self) -> dict[str, dict[str, float | int | bool | None]]:
        now = datetime.now(UTC)
        month = self._month_key(now)
        usage = self.database.provider_usage(month)
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        elapsed_days = max(1.0, now.day - 1 + now.hour / 24)
        result: dict[str, dict[str, float | int | bool | None]] = {}
        for name, bucket in self._buckets.items():
            calls = usage.get(name, 0)
            projected = int(calls / elapsed_days * days_in_month)
            result[name] = {
                "calls_this_month": calls,
                "projected_monthly_calls": projected,
                "monthly_limit": bucket.plan.monthly_limit,
                "requests_per_minute": bucket.plan.requests_per_minute,
                "effective_requests_per_minute": round(
                    _effective_requests_per_minute(bucket.plan, critical=False), 3
                ),
                "reserve_fraction": bucket.plan.reserve_fraction,
                "monthly_pacing": bucket.plan.pace_monthly,
                "billable": bucket.plan.billable,
                "billable_allowed": self.allow_billable,
            }
        return result


DEFAULT_PLANS = [
    ProviderPlan("solana", requests_per_minute=120, monthly_limit=None),
    ProviderPlan("dexscreener", requests_per_minute=300, monthly_limit=None),
    ProviderPlan("jupiter", requests_per_minute=30, monthly_limit=None),
    ProviderPlan("ollama", requests_per_minute=30, monthly_limit=None),
]


def _effective_requests_per_minute(plan: ProviderPlan, *, critical: bool) -> float:
    if plan.monthly_limit is None or not plan.pace_monthly:
        return float(plan.requests_per_minute)
    now = datetime.now(UTC)
    minutes = calendar.monthrange(now.year, now.month)[1] * 24 * 60
    reserve = 0 if critical else int(plan.monthly_limit * plan.reserve_fraction)
    paced_limit = max(1, plan.monthly_limit - reserve)
    return min(float(plan.requests_per_minute), paced_limit / minutes)


def _bucket_capacity(plan: ProviderPlan, effective_rpm: float | None = None) -> float:
    rate = (
        _effective_requests_per_minute(plan, critical=False)
        if effective_rpm is None
        else effective_rpm
    )
    # Permit at most two seconds of burst traffic. A full minute of initial tokens would violate
    # providers that publish their limits per second even when the configured RPM is equivalent.
    return max(1.0, min(float(plan.requests_per_minute), rate / 30.0))
