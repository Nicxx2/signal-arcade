"""Exercise the real receive/retry loop with synthetic time and no networking."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import signal_arcade.providers.solana as solana


def provider():
    return solana.SolanaLogProvider(
        "wss://primary.invalid", Path(__file__).parents[1] / "backend/signal_arcade/resources/idl"
    )


def ack(index):
    return {"id": index, "result": index + 100}


def notification():
    return {
        "method": "logsNotification",
        "params": {
            "subscription": 101,
            "result": {
                "context": {"slot": 10},
                "value": {"signature": "fixture", "err": None, "logs": []},
            },
        },
    }


def run_recovery(monkeypatch, messages, *, final_error=None, end_after=7):
    value, stop = provider(), asyncio.Event()
    clock, delays, attempts = [0.0], [], []
    monkeypatch.setattr(solana, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    class Connection:
        async def __aenter__(self):
            attempts.append(1)
            if len(attempts) <= 6:
                raise OSError("secret-path")
            return self

        async def __aexit__(self, *_):
            pass

        async def send(self, _):
            pass

        async def recv(self):
            if not messages:
                raise final_error or OSError("private-body")
            clock[0], message = messages.pop(0)
            return json.dumps(message)

    monkeypatch.setattr(solana.websockets, "connect", lambda *a, **k: Connection())

    async def wait(_stop, delay):
        delays.append(delay)
        if len(delays) == end_after:
            stop.set()

    monkeypatch.setattr(value, "_wait_retry", wait)

    async def handler(_):
        pytest.fail("empty logs cannot create evidence")

    asyncio.run(value.run(handler, stop))
    assert delays[:6] == [1, 2, 4, 8, 16, 30]
    assert not value.connected and value.next_retry_at is None
    assert "secret" not in json.dumps(value.telemetry.event())
    return delays[-1]


@pytest.mark.parametrize("elapsed,expected", [(59.999999, 30), (60, 1), (60.000001, 1), (2700, 1)])
def test_stable_receive_activity_resets_an_established_failure_streak(
    monkeypatch, elapsed, expected
):
    assert (
        run_recovery(monkeypatch, [(0, ack(1)), (0, ack(2)), (elapsed, notification())]) == expected
    )


def test_stability_does_not_leak_into_the_next_short_flap(monkeypatch):
    assert (
        run_recovery(monkeypatch, [(0, ack(1)), (0, ack(2)), (60, notification())], end_after=8)
        == 2
    )


@pytest.mark.parametrize("direction", [-1, 1])
def test_wall_clock_jumps_do_not_change_monotonic_recovery(monkeypatch, direction):
    calls = [0]

    class JumpingClock:
        @classmethod
        def now(cls, _tz=None):
            calls[0] += 1
            return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=direction * calls[0] * 30)

    monkeypatch.setattr(solana, "datetime", JumpingClock)
    assert run_recovery(monkeypatch, [(0, ack(1)), (0, ack(2)), (60, notification())]) == 1


def test_rejected_subscription_never_qualifies_as_recovery(monkeypatch):
    assert (
        run_recovery(
            monkeypatch, [(0, ack(1)), (60, {"error": {"code": -32000, "message": "secret"}})]
        )
        == 30
    )


@pytest.mark.parametrize(
    "case",
    [
        "quiet",
        "duplicate",
        "one_ack",
        "invalid_ack",
        "same_subscription",
        "wrong_subscription",
        "bad_slot",
        "bad_logs",
        "bad_envelope",
    ],
)
def test_flaps_and_unverified_traffic_cannot_reset_backoff(monkeypatch, case):
    messages = [(0, ack(1)), (0, ack(2))]
    event = notification()
    if case == "quiet":
        messages.append((3600, {"id": 99, "result": 999}))
    elif case == "duplicate":
        messages.append((3600, ack(2)))
    elif case == "one_ack":
        messages = [(0, ack(1)), (3600, event)]
    elif case == "invalid_ack":
        messages = [(0, ack(1)), (0, {"id": 2, "result": True}), (3600, event)]
    elif case == "same_subscription":
        messages = [(0, ack(1)), (0, {"id": 2, "result": 101}), (3600, event)]
    else:
        if case == "wrong_subscription":
            event["params"]["subscription"] = 999
        elif case == "bad_slot":
            event["params"]["result"]["context"]["slot"] = True
        elif case == "bad_logs":
            event["params"]["result"]["value"]["logs"] = [7]
        elif case == "bad_envelope":
            event = []
        messages.append((3600, event))
    assert run_recovery(monkeypatch, messages) == 30


@pytest.mark.parametrize(
    "retry,expected", [("90", 90), ("nan", 60), ("inf", 60), ("-inf", 60), ("secret", 60)]
)
def test_stable_stream_does_not_override_rate_limit_retry(monkeypatch, retry, expected):
    class RateLimited(Exception):
        response = SimpleNamespace(status_code=429, headers={"Retry-After": retry})

    assert (
        run_recovery(
            monkeypatch,
            [(0, ack(1)), (0, ack(2)), (60, notification())],
            final_error=RateLimited("secret"),
        )
        == expected
    )


@pytest.mark.parametrize("trigger", ["stop", "configure", "cancel"])
def test_retry_wait_is_interruptible_without_pending_tasks(trigger):
    async def exercise():
        value, stop = provider(), asyncio.Event()
        task = asyncio.create_task(value._wait_retry(stop, 300))
        await asyncio.sleep(0)
        if trigger == "stop":
            stop.set()
        elif trigger == "configure":
            value.configure("wss://new.invalid")
        else:
            task.cancel()
        if trigger == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await asyncio.wait_for(task, timeout=1)
        assert not [
            t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()
        ]

    asyncio.run(exercise())


@pytest.mark.parametrize("phase", ["connect", "receive"])
def test_reconfiguration_cannot_apply_or_qualify_an_old_connection(monkeypatch, phase):
    value, stop, seen = provider(), asyncio.Event(), []

    class Connection:
        async def __aenter__(self):
            if phase == "connect":
                value.configure("wss://new.invalid")
            return self

        async def __aexit__(self, *_):
            pass

        async def send(self, _):
            pass

        async def recv(self):
            value.configure("wss://new.invalid")
            return json.dumps(notification())

    monkeypatch.setattr(solana.websockets, "connect", lambda *a, **k: Connection())

    async def handler(event):
        seen.append(event)

    asyncio.run(value._run_once(handler, stop))
    assert not seen and not value.connected and not value._attempt_stable
    assert value.telemetry.last_response is None


@pytest.mark.parametrize("phase", ["connect", "receive"])
def test_cancellation_during_stream_attempt_has_no_retry_or_leaked_task(monkeypatch, phase):
    async def exercise():
        value, stop, entered = provider(), asyncio.Event(), asyncio.Event()

        class Connection:
            async def __aenter__(self):
                if phase == "connect":
                    entered.set()
                    await asyncio.Event().wait()
                return self

            async def __aexit__(self, *_):
                pass

            async def send(self, _):
                pass

            async def recv(self):
                entered.set()
                await asyncio.Event().wait()

        monkeypatch.setattr(solana.websockets, "connect", lambda *a, **k: Connection())

        async def handler(_):
            pytest.fail("cancelled stream cannot publish")

        task = asyncio.create_task(value.run(handler, stop))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert value.reconnects == 0 and not value.connected and value.next_retry_at is None
        assert value.telemetry.counts["cancelled"] == 1

    asyncio.run(exercise())
