"""Provider context boundaries also apply inside batches and to failure attribution."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import signal_arcade.providers.solana as solana
from signal_arcade.providers.http import HttpProviders


@pytest.mark.parametrize("boundary", ["configure", "stop", "none"])
def test_stream_boundary_between_decoded_events_stops_old_batch(monkeypatch, boundary):
    provider = solana.SolanaLogProvider(
        "wss://old.invalid", Path(__file__).parents[1] / "backend/signal_arcade/resources/idl"
    )
    stop = asyncio.Event()
    seen = []
    messages = [
        {"id": 1, "result": 101},
        {"id": 2, "result": 102},
        {"params": {"result": {"context": {"slot": 10}, "value": {"logs": []}}}},
    ]
    events = [object(), object()]
    monkeypatch.setattr(provider, "events_from_logs", lambda *_args: events)

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def send(self, _message):
            pass

        async def recv(self):
            return json.dumps(messages.pop(0))

    monkeypatch.setattr(solana.websockets, "connect", lambda *_a, **_k: Connection())

    async def handler(event):
        seen.append(event)
        # The real handler can yield under protected-event backpressure.
        await asyncio.sleep(0)
        if boundary == "configure":
            provider.configure("wss://new.invalid")
        elif boundary == "stop" or len(seen) == len(events):
            stop.set()

    asyncio.run(provider._run_once(handler, stop))
    assert seen == (events if boundary == "none" else events[:1])


@pytest.mark.parametrize("old_response", [200, 403, "transport"])
def test_obsolete_fallback_retains_its_actual_role_only_in_old_scope(old_response):
    async def exercise():
        provider = HttpProviders(
            SimpleNamespace(acquire=AsyncMock(return_value=True)),
            solana_http="https://primary.invalid",
            solana_fallback_http="https://fallback.invalid",
            jupiter_base="https://unused.invalid",
        )
        old = provider.telemetry
        requests = []

        def response(request):
            requests.append(request.url.host)
            if request.url.host == "primary.invalid":
                return httpx.Response(503)
            provider.configure_solana("https://new.invalid")
            if old_response == "transport":
                raise httpx.ReadTimeout("private-provider-text", request=request)
            return httpx.Response(old_response, json={"result": {}})

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        try:
            assert await provider._solana_rpc_response({"method": "getMultipleAccounts"}) is None
            assert requests == ["primary.invalid", "fallback.invalid"]
            assert old.last_failure["category"] == "context_changed"
            assert old.last_failure["role"] == "fallback"
            assert not any(provider.telemetry.counts.values())
            assert not any(provider._solana_unavailable_until.values())
        finally:
            await provider.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", ["reconfigure", "cancel"])
def test_pre_dispatch_boundary_has_no_claimed_endpoint_role(outcome):
    async def exercise():
        quota = SimpleNamespace()
        provider = HttpProviders(
            quota, solana_http="https://primary.invalid", jupiter_base="https://unused.invalid"
        )
        old = provider.telemetry

        async def acquire(*_a, **_k):
            if outcome == "cancel":
                raise asyncio.CancelledError
            provider.configure_solana("https://new.invalid")
            return False

        quota.acquire = acquire
        provider.client.post = AsyncMock(side_effect=AssertionError("no dispatch expected"))
        try:
            if outcome == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await provider._solana_rpc_response({})
            else:
                assert await provider._solana_rpc_response({}) is None
            assert old.last_failure["role"] == "unknown"
            assert old.counts["attempt"] == 0
        finally:
            await provider.close()

    asyncio.run(exercise())
