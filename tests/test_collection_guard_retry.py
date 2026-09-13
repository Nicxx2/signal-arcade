"""Exercise the real reserve worker loop with an isolated virtual clock."""

import asyncio
from types import SimpleNamespace

import pytest
from signal_arcade.orchestrator import Orchestrator


class GuardProbe:
    def __init__(self, *, reason="maintenance", inner=False, ending="success", until=40):
        self.now = 0.0
        self.reason = reason
        self.inner = inner
        self.ending = ending
        self.until = until
        self.calls = []
        self.waits = []
        self.deferrals = []
        self.settings = SimpleNamespace(learning_reserve_refresh_interval_seconds=10)
        self.stop_event = SimpleNamespace(is_set=lambda: self.now >= self.until)
        self._learning_refresh_status = {"worker_errors": 0}

    def blocked(self):
        if self.reason in {"disabled", "demo"}:
            return self.reason
        # Even a 200ms maintenance operation can coincide with every old 10s poll.
        return self.reason if self.reason and self.now % 10 < 0.2 else None

    def _learning_reserve_blocked_reason(self):
        return None if self.inner else self.blocked()

    def _learning_refresh_deferred(self, reason):
        self.deferrals.append((self.now, reason))

    async def _learning_reserve_tick(self):
        reason = self.blocked() if self.inner else None
        if reason:
            self._learning_refresh_deferred(reason)
            return reason
        self.calls.append(self.now)
        self.now += 1
        if self.ending == "cancel":
            raise asyncio.CancelledError
        if self.ending == "error":
            raise TimeoutError("isolated provider timeout")
        return None

    async def _wait_for_stop(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


@pytest.mark.parametrize("inner", [False, True])
@pytest.mark.parametrize(
    "reason",
    [
        "maintenance",
        "market_boundary",
        "pending_sell",
        "queue_pressure",
        "processing_lag",
        "market_unhealthy",
    ],
)
def test_short_guard_deferrals_recover_without_accelerating_requests(inner, reason):
    probe = GuardProbe(inner=inner, reason=reason)
    asyncio.run(Orchestrator._learning_reserve_loop(probe))
    assert probe.calls and 0.2 <= probe.calls[0] <= 2
    assert all(b - a >= 11 for a, b in zip(probe.calls, probe.calls[1:], strict=False))
    assert len(probe.waits) < 45


@pytest.mark.parametrize("reason", ["disabled", "demo"])
def test_permanent_guards_do_not_poll_faster(reason):
    probe = GuardProbe(reason=reason)
    asyncio.run(Orchestrator._learning_reserve_loop(probe))
    assert not probe.calls
    assert probe.waits == [10] * 4


@pytest.mark.parametrize("ending", ["success", "empty", "unavailable", "discarded", "error"])
def test_completed_attempts_keep_full_interval(ending):
    probe = GuardProbe(reason=None, ending=ending)
    asyncio.run(Orchestrator._learning_reserve_loop(probe))
    assert probe.calls == [0, 11, 22, 33]
    assert probe.waits == [10] * 4


def test_guard_retry_staggers_and_stays_bounded_during_sustained_pressure():
    probe = GuardProbe(until=50)
    probe.blocked = lambda: "maintenance" if probe.now % 1 < 0.2 else None
    asyncio.run(Orchestrator._learning_reserve_loop(probe))
    assert probe.calls and probe.calls[0] <= 3
    assert all(wait >= 1 for wait in probe.waits)
    assert all(b - a >= 11 for a, b in zip(probe.calls, probe.calls[1:], strict=False))


def test_cancelled_attempt_does_not_retry():
    probe = GuardProbe(reason=None, ending="cancel")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(Orchestrator._learning_reserve_loop(probe))
    assert probe.calls == [0] and not probe.waits


def test_long_configured_interval_is_preserved_after_attempts():
    probe = GuardProbe(reason=None, until=700)
    probe.settings.learning_reserve_refresh_interval_seconds = 300
    asyncio.run(Orchestrator._learning_reserve_loop(probe))
    assert probe.calls == [0, 301, 602]
    assert probe.waits == [300] * 3


def test_sustained_pressure_never_selects_work_or_spins():
    probe = GuardProbe(until=100)
    probe.blocked = lambda: "queue_pressure"
    asyncio.run(Orchestrator._learning_reserve_loop(probe))
    assert not probe.calls
    assert 75 <= len(probe.waits) <= 100
    assert all(1 <= wait <= 1.25 for wait in probe.waits)
