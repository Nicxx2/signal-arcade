"""Provider diagnostics describe failures without changing requests or leaking text."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, DiagnosticsStore, encode, read_events
from signal_arcade.providers.http import HttpProviders
from signal_arcade.providers.solana import SolanaLogProvider
from signal_arcade.providers.telemetry import MAX_COUNT, ProviderTelemetry, SubscriptionError
from test_publication_backlog import collect, reports


@pytest.mark.parametrize(
    "status", [200, 301, 307, 401, 403, 408, 413, 418, 429, 500, 502, 503, 504]
)
@pytest.mark.parametrize("reporting", ["normal", "disabled", "broken"])
def test_http_reporting_is_observational(status, reporting):
    async def exercise():
        quota = SimpleNamespace(acquire=AsyncMock(return_value=True))
        provider = HttpProviders(
            quota,
            solana_http="https://primary.invalid/secret",
            solana_fallback_http="https://fallback.invalid/secret",
            jupiter_base="https://unused.invalid",
        )
        calls = []

        def response(request):
            calls.append(request.url.host)
            return httpx.Response(status if len(calls) == 1 else 200, json={"result": {}})

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        if reporting != "normal":

            def disabled(*_args, **_kwargs):
                if reporting == "broken":
                    raise RuntimeError("secret")

            provider.telemetry.record = disabled
        result = await provider._solana_rpc_response({"method": "getMultipleAccounts"})
        failover = status in {401, 403, 413, 429} or status >= 500
        assert calls == (
            ["primary.invalid", "fallback.invalid"] if failover else ["primary.invalid"]
        )
        assert result.status_code == (200 if failover else status)
        quota.acquire.assert_awaited_once_with("solana", critical=False)
        if reporting == "normal":
            counts = provider.telemetry.counts
            assert counts["batch"] == 1 and counts["attempt"] == len(calls)
            assert counts["http"] == int(status >= 300)
            assert counts["response"] == int(failover or status == 200)
            if counts["response"]:
                assert provider.telemetry.last_response["operation"] == "accounts"
                assert provider.telemetry.last_response["role"] == (
                    "fallback" if failover else "primary"
                )
            assert "secret" not in json.dumps(provider.telemetry.event())
        await provider.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["transport", "cancelled", "malformed", "rpc"])
def test_handled_and_propagated_failures_are_distinct(case):
    async def exercise():
        provider = HttpProviders(
            SimpleNamespace(acquire=AsyncMock(return_value=True)),
            solana_http="https://rpc.invalid",
            jupiter_base="https://unused.invalid",
        )

        def response(request):
            if case == "transport":
                raise httpx.ReadTimeout("private-url", request=request)
            if case == "cancelled":
                raise asyncio.CancelledError
            if case == "malformed":
                return httpx.Response(200, content=b"invalid-secret-json")
            return httpx.Response(200, json={"error": {"code": -32005, "message": "secret"}})

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        if case == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await provider._solana_rpc_response({"method": "getAccountInfo"})
        else:
            await provider._solana_rpc_response({"method": "getAccountInfo"})
        assert provider.telemetry.counts[case] == 1
        assert "secret" not in json.dumps(provider.telemetry.event())
        await provider.close()

    asyncio.run(exercise())


def test_safe_errors_never_retain_urls_bodies_or_arbitrary_exception_names():
    provider = SolanaLogProvider(
        "wss://user:password@secret.example/path-key?q=query-key#fragment",
        Path(__file__).parents[1] / "backend/signal_arcade/resources/idl",
    )

    class SecretException(Exception):
        response = SimpleNamespace(status_code=413)

    assert (
        provider._safe_error(SecretException("everything-is-secret"))
        == "primary stream: http (413)"
    )
    assert (
        provider._safe_error(SubscriptionError({"nested": "secret"}))
        == "primary stream: subscription"
    )
    assert (
        provider._safe_error(SubscriptionError(-32000)) == "primary stream: subscription (-32000)"
    )


def test_saturated_report_fits_and_optional_admission_preserves_proof(tmp_path):
    telemetry = ProviderTelemetry("http")
    telemetry.counts = {key: MAX_COUNT - i * 157982733777 for i, key in enumerate(telemetry.counts)}
    telemetry.statuses = {
        key: MAX_COUNT - i * 778376439877 for i, key in enumerate(telemetry.statuses)
    }
    telemetry.record("rpc", code=-32005, retry=300, operation="transaction", role="fallback")
    telemetry.record("attempt")
    telemetry.record("response")
    event = telemetry.event()
    assert len(encode(event)) <= MAX_EVENT_PAYLOAD
    recorder = DiagnosticsRecorder(tmp_path)
    for _ in range(4):
        recorder.publication(reports(proofs=6))
    recorder.optional_events([event])
    for _ in range(4):
        selected = recorder._take_events(100)
        assert len([e for e in selected if e["kind"] in {"training", "proof"}]) == 7
        assert len(selected) <= 8
    recorder.enabled = False
    recorder.optional_events([event])
    assert not recorder.events


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), True, "secret", {}, []]
)
def test_untrusted_codes_and_nonfinite_retry_do_not_escape(value):
    telemetry = ProviderTelemetry("http")
    telemetry.record("http", code=value, retry=float("nan"), role="secret", operation="secret")
    encoded = json.dumps(telemetry.event(), allow_nan=False)
    assert "secret" not in encoded
    assert telemetry.last_failure["code"] is None
    assert telemetry.last_failure["retry"] == 0


def test_provider_report_survives_persistence_alongside_complete_proof(tmp_path):
    telemetry = ProviderTelemetry("http")
    telemetry.record("http", code=413, role="fallback", operation="accounts")
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.publication(reports(proofs=6))
    recorder.optional_events([telemetry.event()])
    interval = collect(recorder)
    store = DiagnosticsStore(tmp_path)
    try:
        assert store.append(interval)
        assert store.append(interval)
    finally:
        store.close()
    records = [
        row["record"] for row in read_events(tmp_path, before=interval["end"] + 1, limit=100)
    ]
    assert len(records) == 8
    assert sum(r["kind"] == "proof" for r in records) == 6
    report = next(r for r in records if r["kind"] == "provider_health")
    assert report["last_failure"]["code"] == 413
    assert report["counts"]["http"] == 1 and report["scope"] == telemetry.scope
