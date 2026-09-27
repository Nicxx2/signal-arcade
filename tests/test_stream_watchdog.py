"""Silent application subscriptions, without network or real-time sleeps."""

import asyncio
import json
from types import SimpleNamespace

import pytest
import signal_arcade.providers.solana as solana
from test_provider_recovery import ack, notification, provider


def exercise(monkeypatch, messages, *, handler_seconds=0):
    value, stop = provider(), asyncio.Event()
    clock, sends, delays = [0.0], [], []
    monkeypatch.setattr(solana, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def send(self, raw):
            sends.append(json.loads(raw))

        async def recv(self):
            if messages:
                elapsed, message = messages.pop(0)
                clock[0] += elapsed
                if message is None:
                    raise TimeoutError
                if message == "stop":
                    stop.set()
                    raise TimeoutError
                return json.dumps(message)
            clock[0] += 30
            raise TimeoutError

        async def ping(self):
            pass

    monkeypatch.setattr(solana.websockets, "connect", lambda *a, **kw: Connection())
    if handler_seconds:
        monkeypatch.setattr(value, "events_from_logs", lambda *_: [object()])

    async def handler(_):
        clock[0] += handler_seconds

    async def wait(_stop, delay):
        delays.append(delay)
        stop.set()

    monkeypatch.setattr(value, "_wait_retry", wait)
    asyncio.run(value.run(handler, stop))
    assert len(sends) == 2
    return value, clock[0], delays


@pytest.mark.parametrize("acks", [0, 1, 2])
def test_ping_only_connection_cannot_wait_forever(monkeypatch, acks):
    value, elapsed, delays = exercise(monkeypatch, [(0, ack(i + 1)) for i in range(acks)])
    assert elapsed == (180 if acks == 2 else 30)
    assert value.reconnects == 1 and delays == [1]
    assert not value.connected and value.next_retry_at is None
    assert value.last_notification_at is None
    assert ("notification_idle" if acks == 2 else "subscription_setup") in value.last_error


@pytest.mark.parametrize("junk", [ack(1), {"id": 99, "result": 9}])
def test_unrelated_frames_do_not_extend_setup(monkeypatch, junk):
    value, elapsed, _ = exercise(monkeypatch, [(10, junk)] * 20)
    assert value.reconnects == 1 and elapsed == 30


def test_wrong_subscription_cannot_extend_idle_deadline(monkeypatch):
    wrong = notification()
    wrong["params"]["subscription"] = 999
    value, elapsed, _ = exercise(monkeypatch, [(0, ack(1)), (0, ack(2)), *[(30, wrong)] * 10])
    assert elapsed == 180 and value.reconnects == 1
    assert value.last_notification_at is None


@pytest.mark.parametrize(
    "error",
    [None, {"InstructionError": [0, "fixture"]}, "AccountNotFound", "InvalidProgramForExecution"],
)
def test_valid_notifications_without_trades_keep_one_feed_healthy(monkeypatch, error):
    event = notification()
    event["params"]["result"]["value"]["err"] = error
    if error is not None:

        def cannot_decode(*_):
            pytest.fail("Failed transactions cannot generate market events")

        monkeypatch.setattr(solana.SolanaLogProvider, "events_from_logs", cannot_decode)
    value, _, delays = exercise(
        monkeypatch, [(0, ack(1)), (0, ack(2)), *[(100, event)] * 10, (0, "stop")]
    )
    assert value.reconnects == 0 and not delays
    assert value.last_notification_at is not None


@pytest.mark.parametrize("error", [False, 17, [], ["InstructionError"]])
def test_malformed_error_values_cannot_keep_stream_alive(monkeypatch, error):
    event = notification()
    event["params"]["result"]["value"]["err"] = error
    value, _, delays = exercise(monkeypatch, [(0, ack(1)), (0, ack(2)), *[(30, event)] * 10])
    assert value.reconnects == 1 and delays == [1]
    assert value.last_notification_at is None


def test_slow_local_handler_does_not_force_provider_reconnect(monkeypatch):
    value, elapsed, delays = exercise(
        monkeypatch,
        [(0, ack(1)), (0, ack(2)), (1, notification()), (30, None), (0, "stop")],
        handler_seconds=600,
    )
    assert elapsed == 631 and value.reconnects == 0 and not delays


def test_first_subscription_handler_cannot_expire_buffered_second_ack(monkeypatch):
    value, elapsed, delays = exercise(
        monkeypatch,
        [(0, ack(1)), (1, notification()), (0, ack(2)), (0, "stop")],
        handler_seconds=600,
    )
    assert elapsed == 601 and value.reconnects == 0 and not delays


def test_quiet_period_below_limit_is_not_a_gap(monkeypatch):
    value, _, delays = exercise(
        monkeypatch, [(0, ack(1)), (0, ack(2)), *[(30, None)] * 5, (1, notification()), (0, "stop")]
    )
    assert value.reconnects == 0 and not delays


@pytest.mark.parametrize("blocked", ["subscribe", "ping"])
def test_stalled_send_cannot_leave_recovery_waiting_forever(monkeypatch, blocked):
    value, stop = provider(), asyncio.Event()
    messages = [ack(1), ack(2)]
    monkeypatch.setattr(solana, "SUBSCRIPTION_SETUP_SECONDS", 0.05)
    monkeypatch.setattr(solana, "NOTIFICATION_IDLE_SECONDS", 0.05)

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def send(self, _):
            if blocked == "subscribe":
                await asyncio.Event().wait()

        async def recv(self):
            if messages:
                return json.dumps(messages.pop(0))
            raise TimeoutError

        async def ping(self):
            await asyncio.Event().wait()

    async def wait(_stop, _delay):
        stop.set()

    async def run():
        await asyncio.wait_for(value.run(lambda _: None, stop), timeout=2)

    monkeypatch.setattr(solana.websockets, "connect", lambda *a, **kw: Connection())
    monkeypatch.setattr(value, "_wait_retry", wait)
    asyncio.run(run())
    assert value.reconnects == 1 and not value.connected
    # Send timeouts retain the existing redacted transport-error classification.
    assert value.last_error == "primary stream: transport"
