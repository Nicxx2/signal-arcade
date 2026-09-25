"""Recovery and bounded work at the final v1.10.11 release boundary."""

# ruff: noqa: F811 -- shared fixture

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import signal_arcade.providers.http as http_module
from signal_arcade.providers.http import HttpProviders
from signal_arcade.providers.solana import SolanaLogProvider
from test_probe_retention import engine  # noqa: F401
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response


def test_completed_urgent_cleanup_is_not_a_deferred_pass(engine, monkeypatch):
    # Exercise retry policy with an admitted reader. Real deadline/dispatch tests live in
    # test_maintenance_reads; CPU scheduling must not substitute an unknown-capacity case.
    monkeypatch.setattr(engine.database, "maintenance_read", lambda read, **_: read())
    engine._storage_snapshot["live_bytes"] = engine.storage_max_bytes + 1
    monkeypatch.setattr(engine, "_storage_market_path_busy", lambda: True)
    monkeypatch.setattr(
        engine.database,
        "storage_capacity_stats",
        lambda: {"live_bytes": engine.storage_max_bytes + 1},
    )
    monkeypatch.setattr(engine.database, "prune_history", lambda *_a, **_k: {"raw_trades": 3})
    monkeypatch.setattr(
        engine.database,
        "prune_retired_decisions",
        lambda **_k: {"retired_decisions": 0, "work_remaining": 0},
    )
    monkeypatch.setattr(
        engine.database,
        "enforce_storage_budget",
        lambda *_a, **_k: {"raw_trades": 3, "work_remaining": 1},
    )
    monkeypatch.setattr(
        engine.database,
        "prune_optional_history",
        lambda *_a, **_k: pytest.fail("optional work on busy stream"),
    )
    asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    assert engine._storage_maintenance_last_removed["raw_trades"] == 6
    assert engine._storage_maintenance_requested
    assert engine._storage_maintenance_deferred_reason is None
    assert not engine._storage_maintenance_active and engine._storage_idle.is_set()


@pytest.mark.parametrize(
    "urgent,work_remaining,expected_delay", [(False, True, 2), (True, True, 0.25), (True, False, 5)]
)
def test_cleanup_loop_distinguishes_work_from_pressure_deferral(
    engine, monkeypatch, urgent, work_remaining, expected_delay
):
    monkeypatch.setattr(engine.database, "maintenance_read", lambda read, **_: read())
    live_bytes = engine.storage_max_bytes + 1 if urgent else 0
    monkeypatch.setattr(engine, "_storage_market_path_busy", lambda: True)
    monkeypatch.setattr(
        engine.database, "storage_capacity_stats", lambda: {"live_bytes": live_bytes}
    )
    calls = []

    def history(*_args, **_kwargs):
        calls.append("history")
        return {"raw_trades": 3 if work_remaining else 0, "work_remaining": int(work_remaining)}

    monkeypatch.setattr(engine.database, "prune_history", history)
    monkeypatch.setattr(
        engine.database,
        "prune_retired_decisions",
        lambda **_k: {"retired_decisions": 0, "work_remaining": 0},
    )
    monkeypatch.setattr(
        engine.database,
        "enforce_storage_budget",
        lambda *_a, **_k: {
            "raw_trades": 3 if work_remaining else 0,
            "work_remaining": int(work_remaining),
        },
    )
    waits = []

    async def wait(delay):
        waits.append(delay)
        if len(waits) == 2:
            engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    asyncio.run(engine._storage_loop())
    assert waits == [15, expected_delay]
    assert calls == (["history"] if urgent else [])
    assert not engine._storage_maintenance_active and engine._storage_idle.is_set()
    if urgent and not work_remaining:
        assert engine._storage_budget_state == "retained_evidence_above_target"
        assert not engine._storage_maintenance_requested


def test_http_413_uses_configured_fallback_and_backoff():
    async def exercise():
        provider = HttpProviders(
            SimpleNamespace(acquire=AsyncMock(return_value=True)),
            solana_http="https://primary.invalid",
            solana_fallback_http="https://fallback.invalid",
            jupiter_base="https://unused.invalid",
        )
        calls = []

        def response(request):
            calls.append(request.url.host)
            return httpx.Response(
                413 if request.url.host == "primary.invalid" else 200, json={"result": {}}
            )

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        try:
            result = await provider._solana_rpc_response({"method": "getMultipleAccounts"})
            assert result is not None and result.status_code == 200
            assert calls == ["primary.invalid", "fallback.invalid"]
            assert provider._solana_unavailable_until["primary"] > 0
            assert provider.telemetry.statuses[413] == 1
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_websocket_413_uses_only_configured_fallback_once():
    provider = SolanaLogProvider(
        "wss://primary.invalid",
        Path(__file__).parents[1] / "backend/signal_arcade/resources/idl",
        fallback_ws_url="wss://fallback.invalid",
    )
    error = httpx.HTTPStatusError(
        "private",
        request=httpx.Request("GET", "https://primary.invalid"),
        response=httpx.Response(413),
    )
    assert provider._activate_fallback(error)
    assert provider.active_ws_url == "wss://fallback.invalid"
    assert provider.fallback_reason == "primary_http_413"
    assert not provider._activate_fallback(error)


@pytest.mark.parametrize("fallback", [None, "https://fallback.invalid"])
@pytest.mark.parametrize("critical", [False, True])
def test_all_413_failures_are_unknown_and_cool_down_without_changing_requests(fallback, critical):
    async def exercise():
        quota = SimpleNamespace(acquire=AsyncMock(return_value=True))
        provider = HttpProviders(
            quota,
            solana_http="https://primary.invalid",
            solana_fallback_http=fallback,
            jupiter_base="https://unused.invalid",
        )
        calls = []
        body = {
            "method": "getMultipleAccounts",
            "params": [["curve", "mint"], {"minContextSlot": 123, "commitment": "confirmed"}],
        }

        def response(request):
            import json

            calls.append(json.loads(request.content))
            return httpx.Response(413, headers={"Retry-After": "120"})

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        try:
            assert await provider._solana_rpc_response(body, critical=critical) is None
            assert calls == [body] * (2 if fallback else 1)
            assert await provider._solana_rpc_response(body, critical=critical) is None
            assert len(calls) == (2 if fallback else 1)
            quota.acquire.assert_awaited_once_with("solana", critical=critical)
            assert provider.telemetry.counts["response"] == 0
            assert provider.telemetry.last_failure["retry"] > 100
            assert provider.telemetry.counts["cooldown"] == 1
        finally:
            await provider.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("status", [400, 401, 403, 408, 500])
def test_unrelated_websocket_errors_do_not_gain_new_failover(status):
    provider = SolanaLogProvider(
        "wss://primary.invalid",
        Path(__file__).parents[1] / "backend/signal_arcade/resources/idl",
        fallback_ws_url="wss://fallback.invalid",
    )
    error = httpx.HTTPStatusError(
        "private",
        request=httpx.Request("GET", "https://primary.invalid"),
        response=httpx.Response(status),
    )
    assert not provider._activate_fallback(error)
    assert provider.active_ws_url == "wss://primary.invalid"


def test_413_stream_without_fallback_keeps_bounded_backoff():
    provider = SolanaLogProvider(
        "wss://primary.invalid", Path(__file__).parents[1] / "backend/signal_arcade/resources/idl"
    )
    error = httpx.HTTPStatusError(
        "private",
        request=httpx.Request("GET", "https://primary.invalid"),
        response=httpx.Response(413),
    )
    assert not provider._activate_fallback(error)
    assert provider._retry_backoff(error, 16) == (16, 30)
    assert provider._retry_backoff(error, 30) == (30, 30)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("90", (90, 180)),
        ("9999", (300, 300)),
        ("nan", (16, 30)),
        ("inf", (16, 30)),
        ("-1", (16, 30)),
        ("invalid", (16, 30)),
    ],
)
def test_413_stream_retry_after_is_bounded_and_untrusted(header, expected):
    error = httpx.HTTPStatusError(
        "private",
        request=httpx.Request("GET", "https://primary.invalid"),
        response=httpx.Response(413, headers={"Retry-After": header}),
    )
    assert SolanaLogProvider._retry_backoff(error, 16) == expected


def test_real_websocket_handshake_413_retains_retry_and_safe_failure():
    provider = SolanaLogProvider(
        "wss://primary.invalid",
        Path(__file__).parents[1] / "backend/signal_arcade/resources/idl",
        fallback_ws_url="wss://fallback.invalid",
    )
    error = InvalidStatus(Response(413, "private-provider-text", Headers({"Retry-After": "90"})))
    assert provider._retry_backoff(error, 1) == (90, 180)
    assert provider._safe_error(error) == "primary stream: http (413)"
    assert provider._activate_fallback(error)
    assert provider.fallback_reason == "primary_http_413"
    assert not provider.connected


def test_http_413_cooldown_expires_and_success_resets_failures(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(http_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def exercise():
        provider = HttpProviders(
            SimpleNamespace(acquire=AsyncMock(return_value=True)),
            solana_http="https://primary.invalid",
            jupiter_base="https://unused.invalid",
        )
        calls = []

        def response(request):
            calls.append(request.url.host)
            return httpx.Response(
                413 if len(calls) == 1 else 200,
                headers={"Retry-After": "10"},
                json={"result": {}},
            )

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        try:
            assert await provider._solana_rpc_response({}) is None
            clock[0] = 109.999
            assert await provider._solana_rpc_response({}) is None
            assert len(calls) == 1
            clock[0] = 110.0
            result = await provider._solana_rpc_response({})
            assert result is not None and result.status_code == 200
            assert calls == ["primary.invalid", "primary.invalid"]
            assert provider._solana_failures["primary"] == 0
            assert provider._solana_unavailable_until["primary"] == 0
        finally:
            await provider.close()

    asyncio.run(exercise())
