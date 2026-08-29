from __future__ import annotations

import asyncio
import base64
import json
import struct
from pathlib import Path

import httpx
import pytest
from signal_arcade.database import Database
from signal_arcade.providers.http import (
    SPL_TOKEN_PROGRAM,
    TOKEN_2022_PROGRAM,
    HttpProviders,
    ProviderError,
    _float,
    _token_2022_extension_types,
)
from signal_arcade.quota import ProviderPlan, QuotaBroker


def test_mint_safety_reads_authorities_supply_and_decimals(tmp_path: Path) -> None:
    raw = bytearray(82)
    struct.pack_into("<I", raw, 0, 0)
    struct.pack_into("<Q", raw, 36, 1_000_000_000_000_000)
    raw[44] = 6
    raw[45] = 1
    struct.pack_into("<I", raw, 46, 0)

    def response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {
                    "value": {
                        "owner": SPL_TOKEN_PROGRAM,
                        "data": [base64.b64encode(raw).decode(), "base64"],
                    }
                }
            },
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("solana", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        result = await providers.solana_mint_safety("Mint111111111111111111111111111111111111111")
        assert result is not None
        assert result["safe"] is True
        assert result["mint_authority_revoked"] is True
        assert result["freeze_authority_revoked"] is True
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_batched_mint_safety_reuses_the_same_fail_closed_decoder() -> None:
    raw = bytearray(82)
    struct.pack_into("<I", raw, 0, 0)
    struct.pack_into("<Q", raw, 36, 1_000_000_000_000_000)
    raw[44] = 6
    raw[45] = 1
    struct.pack_into("<I", raw, 46, 0)

    safe = HttpProviders.mint_safety_from_account({"owner": SPL_TOKEN_PROGRAM, "raw": bytes(raw)})
    assert safe is not None
    assert safe["safe"] is True
    assert safe["verified"] is True
    assert HttpProviders.mint_safety_from_account(None) is None
    assert HttpProviders.mint_safety_from_account({"owner": SPL_TOKEN_PROGRAM}) is None

    wrong_owner = HttpProviders.mint_safety_from_account(
        {"owner": "malicious-owner", "raw": bytes(raw)}
    )
    assert wrong_owner is not None
    assert wrong_owner["safe"] is False
    assert "unsupported_account_owner" in wrong_owner["failures"]


def test_mint_safety_falls_back_when_keyed_rpc_is_rate_limited(tmp_path: Path) -> None:
    raw = bytearray(82)
    struct.pack_into("<I", raw, 0, 0)
    struct.pack_into("<Q", raw, 36, 1_000_000_000_000_000)
    raw[44] = 6
    raw[45] = 1
    struct.pack_into("<I", raw, 46, 0)
    calls: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "keyed.invalid":
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(
            200,
            json={
                "result": {
                    "value": {
                        "owner": SPL_TOKEN_PROGRAM,
                        "data": [base64.b64encode(raw).decode(), "base64"],
                    }
                }
            },
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("solana", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://keyed.invalid",
        solana_fallback_http="https://public.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        result = await providers.solana_mint_safety("Mint111111111111111111111111111111111111111")
        assert result is not None
        assert result["safe"] is True
        await providers.close()

    asyncio.run(exercise())
    assert calls == ["keyed.invalid", "public.invalid"]
    database.close()


def test_ollama_streamed_pull_error_is_not_hidden(tmp_path: Path) -> None:
    def response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"status":"pulling manifest"}\n{"error":"registry unavailable"}\n',
            headers={"content-type": "application/x-ndjson"},
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        with pytest.raises(ProviderError, match="registry unavailable"):
            await providers.pull_ollama_model("qwen3.5:4b", lambda _: None)
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_token_2022_extensions_are_read_after_padded_mint_base() -> None:
    metadata_pointer = bytearray(166 + 4 + 64)
    metadata_pointer[165] = 1  # AccountType::Mint
    struct.pack_into("<HH", metadata_pointer, 166, 18, 64)
    assert _token_2022_extension_types(metadata_pointer) == [18]

    transfer_fee = bytearray(170)
    transfer_fee[165] = 1
    struct.pack_into("<HH", transfer_fee, 166, 1, 0)
    assert _token_2022_extension_types(transfer_fee) == [1]

    current_pump_metadata = bytearray(166 + 4 + 64 + 4 + 40)
    current_pump_metadata[165] = 1
    struct.pack_into("<HH", current_pump_metadata, 166, 18, 64)
    struct.pack_into("<HH", current_pump_metadata, 234, 19, 40)
    assert _token_2022_extension_types(current_pump_metadata) == [18, 19]


def test_current_pump_metadata_only_token_2022_mint_is_safe(tmp_path: Path) -> None:
    raw = bytearray(166 + 4 + 64 + 4 + 40)
    struct.pack_into("<I", raw, 0, 0)
    struct.pack_into("<Q", raw, 36, 1_000_000_000_000_000)
    raw[44] = 6
    raw[45] = 1
    struct.pack_into("<I", raw, 46, 0)
    raw[165] = 1
    struct.pack_into("<HH", raw, 166, 18, 64)
    struct.pack_into("<HH", raw, 234, 19, 40)

    def response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {
                    "value": {
                        "owner": TOKEN_2022_PROGRAM,
                        "data": [base64.b64encode(raw).decode(), "base64"],
                    }
                }
            },
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("solana", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        result = await providers.solana_mint_safety("Mint111111111111111111111111111111111111111")
        assert result is not None
        assert result["safe"] is True
        assert result["extension_types"] == [18, 19]
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_critical_account_check_falls_back_when_keyed_rpc_is_rate_limited(
    tmp_path: Path,
) -> None:
    raw = b"verified-pool-account"
    calls: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "keyed.invalid":
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(
            200,
            json={
                "result": {
                    "value": {
                        "owner": "program-owner",
                        "lamports": 1,
                        "executable": False,
                        "data": [base64.b64encode(raw).decode(), "base64"],
                    }
                }
            },
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("solana", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://keyed.invalid",
        solana_fallback_http="https://public.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        result = await providers.solana_account_info("Pool111", critical=True)
        assert result is not None
        assert result["owner"] == "program-owner"
        assert result["raw"] == raw
        await providers.close()

    asyncio.run(exercise())
    assert calls == ["keyed.invalid", "public.invalid"]
    database.close()


def test_solana_primary_cooldown_does_not_block_batched_public_fallback(
    tmp_path: Path,
) -> None:
    raw = b"account"
    calls: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "keyed.invalid":
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(
            200,
            json={
                "result": {
                    "context": {"slot": 101},
                    "value": [
                        {
                            "owner": "program-owner",
                            "lamports": 1,
                            "executable": False,
                            "data": [base64.b64encode(raw).decode(), "base64"],
                        }
                    ],
                }
            },
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("solana", requests_per_minute=600)])
    providers = HttpProviders(
        quota,
        solana_http="https://keyed.invalid",
        solana_fallback_http="https://public.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        for _ in range(2):
            result = await providers.solana_multiple_accounts(
                ["Pool111111111111111111111111111111111111111"],
                min_context_slot=100,
            )
            assert result is not None
            assert result["slot"] == 101
            assert result["accounts"]["Pool111111111111111111111111111111111111111"]
        await providers.close()

    asyncio.run(exercise())
    assert calls == ["keyed.invalid", "public.invalid", "public.invalid"]
    database.close()


def test_multiple_accounts_fails_closed_on_partial_or_old_response(tmp_path: Path) -> None:
    responses = [
        {"result": {"context": {"slot": 99}, "value": [None]}},
        {"result": {"context": {"slot": 101}, "value": []}},
    ]

    def response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("solana", requests_per_minute=600)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        address = "Pool111111111111111111111111111111111111111"
        assert await providers.solana_multiple_accounts([address], min_context_slot=100) is None
        assert await providers.solana_multiple_accounts([address], min_context_slot=100) is None
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_token_2022_malformed_padding_and_lengths_fail_closed() -> None:
    bad_padding = bytearray(170)
    bad_padding[82] = 1
    bad_padding[165] = 1
    assert _token_2022_extension_types(bad_padding) == [-1]

    bad_metadata_length = bytearray(170)
    bad_metadata_length[165] = 1
    struct.pack_into("<HH", bad_metadata_length, 166, 18, 0)
    assert _token_2022_extension_types(bad_metadata_length) == [-1]


def test_non_finite_provider_numbers_are_not_exposed() -> None:
    assert _float("NaN") is None
    assert _float("Infinity") is None
    assert _float("not-a-number") is None
    assert _float("12.5") == 12.5


def test_ollama_runtime_reports_actual_cpu_gpu_split(tmp_path: Path) -> None:
    def response(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.33.1"})
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "qwen3.5:4b",
                            "size": 4_000,
                            "size_vram": 3_000,
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected Ollama path: {request.url.path}")

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama:11434",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        status = await providers.ollama_runtime_status()
        assert status == {
            "reachable": True,
            "version": "0.33.1",
            "loaded_model_count": 1,
            "loaded_model_bytes": 4_000,
            "loaded_vram_bytes": 3_000,
            "compute": "hybrid",
        }
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_ollama_runtime_failure_is_optional_and_fallback_safe(tmp_path: Path) -> None:
    def response(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama is starting")

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama:11434",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        status = await providers.ollama_runtime_status()
        assert status["reachable"] is False
        assert status["compute"] == "unavailable"
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_malformed_ollama_payloads_fail_closed(tmp_path: Path) -> None:
    def response(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json=["unexpected"])
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": "not-an-array"})
        raise AssertionError(f"unexpected Ollama path: {request.url.path}")

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama:11434",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        assert (await providers.ollama_runtime_status())["reachable"] is False
        assert await providers.ollama_models() == []
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_ollama_model_removal_uses_exact_model(tmp_path: Path) -> None:
    requested: list[tuple[str, dict[str, str]]] = []

    def response(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, json.loads(request.content)))
        return httpx.Response(200)

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama:11434",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        await providers.delete_ollama_model("qwen3.5:4b")
        await providers.close()

    asyncio.run(exercise())
    assert requested == [("DELETE", {"model": "qwen3.5:4b"})]
    database.close()


def test_ollama_generation_disables_unbounded_thinking(tmp_path: Path) -> None:
    requested: list[dict[str, object]] = []

    def response(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requested.append(body)
        if "format" in body:
            return httpx.Response(200, json={"response": '{"risk_score": 20}'})
        return httpx.Response(200, json={"response": "Evidence-based explanation."})

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=60)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama:11434",
        ollama_model="qwen3.5:4b",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        assert await providers.explain_with_ollama("Explain this decision")
        structured = await providers.ollama_structured(
            prompt="Assess this candidate",
            schema={"type": "object"},
        )
        assert structured is not None
        await providers.close()

    asyncio.run(exercise())
    assert len(requested) == 2
    assert all(body["think"] is False for body in requested)
    assert all(body["options"]["num_ctx"] == 1_024 for body in requested)
    explanation = next(body for body in requested if "format" not in body)
    structured = next(body for body in requested if "format" in body)
    assert explanation["options"]["num_predict"] == 96
    assert structured["options"]["num_predict"] == 96
    assert all(body["keep_alive"] == "10m" for body in requested)
    database.close()


def test_interactive_ollama_explanation_falls_back_when_shadow_is_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = False

    def response(_: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, json={"response": "Should not run."})

    monkeypatch.setattr("signal_arcade.providers.http.OLLAMA_INTERACTIVE_WAIT_SECONDS", 0.01)
    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=60)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama:11434",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        await providers._ollama_generation_lock.acquire()  # noqa: SLF001
        try:
            assert await providers.explain_with_ollama("Explain") is None
        finally:
            providers._ollama_generation_lock.release()  # noqa: SLF001
        await providers.close()

    asyncio.run(exercise())
    assert requested is False
    database.close()


def test_structured_ollama_timeout_includes_waiting_for_the_generation_lock(
    tmp_path: Path,
) -> None:
    requested = False

    def response(_: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, json={"response": "{}"})

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("ollama", requests_per_minute=60)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
        ollama_url="http://ollama:11434",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        await providers._ollama_generation_lock.acquire()  # noqa: SLF001
        try:
            result = await providers.ollama_structured(
                prompt="Assess",
                schema={"type": "object"},
                timeout_seconds=0.01,
            )
            assert result is None
        finally:
            providers._ollama_generation_lock.release()  # noqa: SLF001
        await providers.close()

    asyncio.run(exercise())
    assert requested is False
    database.close()


def test_dexscreener_uses_requested_token_as_base_and_derives_one_sol_usd_rate(
    tmp_path: Path,
) -> None:
    mint = "Mint111111111111111111111111111111111111111"
    wrapped_sol = "So11111111111111111111111111111111111111112"

    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/tokens/v1/solana/{mint}"
        return httpx.Response(
            200,
            json=[
                {
                    "chainId": "solana",
                    "pairAddress": "wrong-direction",
                    "baseToken": {"address": wrapped_sol},
                    "quoteToken": {"address": mint},
                    "priceUsd": "200",
                    "priceNative": "1",
                    "liquidity": {"usd": 9_000_000},
                },
                {
                    "chainId": "solana",
                    "pairAddress": "correct-direction",
                    "baseToken": {
                        "address": mint,
                        "name": "  Correct\x00  Token\n ",
                        "symbol": " OK ",
                    },
                    "quoteToken": {"address": wrapped_sol},
                    "priceUsd": "0.002",
                    "priceNative": "0.00001",
                    "liquidity": {"usd": 50_000},
                    "volume": {"m5": 1_200, "h24": 50_000},
                    "txns": {"m5": {"buys": 12, "sells": 3}},
                    "marketCap": 1_000_000,
                    "fdv": 1_100_000,
                },
            ],
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("dexscreener", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        result = await providers.dexscreener_token(mint)
        assert result is not None
        assert result["pair_address"] == "correct-direction"
        assert result["base_mint"] == mint
        assert result["base_token_name"] == "Correct Token"  # noqa: S105 - display metadata
        assert result["base_token_symbol"] == "OK"  # noqa: S105 - display metadata
        assert result["quote_mint"] == wrapped_sol
        assert result["sol_usd_price"] == 200
        await providers.close()

    asyncio.run(exercise())
    database.close()


def test_dexscreener_rejects_negative_financial_values(tmp_path: Path) -> None:
    mint = "Mint111111111111111111111111111111111111111"

    def response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "chainId": "solana",
                    "baseToken": {"address": mint},
                    "quoteToken": {"address": "So11111111111111111111111111111111111111112"},
                    "priceUsd": "-1",
                    "priceNative": "-0.1",
                    "liquidity": {"usd": -20},
                    "volume": {"m5": -30},
                    "marketCap": -40,
                }
            ],
        )

    database = Database(tmp_path / "quota.sqlite3")
    quota = QuotaBroker(database, [ProviderPlan("dexscreener", requests_per_minute=10)])
    providers = HttpProviders(
        quota,
        solana_http="https://rpc.invalid",
        jupiter_base="https://jupiter.invalid",
    )

    async def exercise() -> None:
        await providers.client.aclose()
        providers.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        result = await providers.dexscreener_token(mint)
        assert result is not None
        assert result["price_usd"] is None
        assert result["price_native"] is None
        assert result["sol_usd_price"] is None
        assert result["liquidity_usd"] is None
        assert result["volume_5m_usd"] is None
        assert result["market_cap_usd"] is None
        await providers.close()

    asyncio.run(exercise())
    database.close()
