"""Old provider operations cannot cool down, clear or apply into a new context."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from signal_arcade.providers.http import HttpProviders
from test_probe_retention import engine  # noqa: F401
from test_reserve_contract_integration import public_config_route


@pytest.mark.parametrize("old_status", [200, 403, 413, 429, 503, "transport"])
@pytest.mark.parametrize("same_url", [False, True])
def test_old_response_cannot_touch_new_endpoint(old_status, same_url):
    async def exercise():
        provider = HttpProviders(
            SimpleNamespace(acquire=AsyncMock(return_value=True)),
            solana_http="https://old.invalid",
            solana_fallback_http="https://fallback.invalid",
            jupiter_base="https://unused.invalid",
        )
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def response(request):
            calls.append(request.url.host)
            if len(calls) == 1:
                entered.set()
                await release.wait()
                if old_status == "transport":
                    raise httpx.ReadTimeout("secret", request=request)
                return httpx.Response(old_status, json={"result": {}})
            return httpx.Response(403)

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        old_telemetry = provider.telemetry
        old = asyncio.create_task(provider._solana_rpc_response({}))
        await entered.wait()
        provider.configure_solana("https://old.invalid" if same_url else "https://new.invalid")
        assert await provider._solana_rpc_response({}) is None
        cooldown = dict(provider._solana_unavailable_until)
        latest = provider.telemetry.event()
        release.set()
        assert await old is None
        assert provider._solana_unavailable_until == cooldown
        current = provider.telemetry.event()
        assert {k: v for k, v in current.items() if k != "at"} == {
            k: v for k, v in latest.items() if k != "at"
        }
        assert old_telemetry.counts["context_changed"] == 1
        assert calls == ["old.invalid", "old.invalid" if same_url else "new.invalid"]
        await provider.close()

    asyncio.run(exercise())


def test_change_during_quota_wait_makes_no_obsolete_request():
    async def exercise():
        quota = SimpleNamespace()
        provider = HttpProviders(
            quota, solana_http="https://old.invalid", jupiter_base="https://unused.invalid"
        )

        async def acquire(*_a, **_k):
            provider.configure_solana("https://new.invalid")
            return True

        quota.acquire = acquire
        provider.client.post = AsyncMock(side_effect=AssertionError("obsolete request"))
        assert await provider._solana_rpc_response({}) is None
        assert provider.telemetry.counts["attempt"] == 0
        await provider.close()

    asyncio.run(exercise())


def test_new_endpoint_is_immediately_available_after_old_forbidden_response():
    async def exercise():
        provider = HttpProviders(
            SimpleNamespace(acquire=AsyncMock(return_value=True)),
            solana_http="https://old.invalid",
            jupiter_base="https://unused.invalid",
        )
        calls = []

        def response(request):
            calls.append(request.url.host)
            if len(calls) == 1:
                provider.configure_solana("https://new.invalid")
                return httpx.Response(403)
            return httpx.Response(200, json={"result": {}})

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        assert await provider._solana_rpc_response({}) is None
        assert (await provider._solana_rpc_response({})).status_code == 200
        assert calls == ["old.invalid", "new.invalid"]
        await provider.close()

    asyncio.run(exercise())


def test_configuration_transition_waits_for_application_boundary(engine, monkeypatch):
    configure = engine.http.configure_solana
    calls = []

    def guarded(*args, **kwargs):
        assert engine._event_lock.locked()
        calls.append(1)
        configure(*args, **kwargs)

    monkeypatch.setattr(engine.http, "configure_solana", guarded)
    monkeypatch.setattr(engine.ai_lab, "refresh_models", AsyncMock())
    generation = engine.http.solana_generation
    policy = engine.learning.coverage_policy

    async def exercise():
        await engine._event_lock.acquire()
        task = asyncio.create_task(engine.configure_providers(engine.provider_configuration, {}))
        await asyncio.sleep(0)
        assert not task.done() and engine.http.solana_generation == generation
        engine._event_lock.release()
        result = await task
        assert not result["source_restarted"]

    asyncio.run(exercise())
    assert calls == [1] and engine.http.solana_generation == generation + 1
    assert engine.learning.coverage_policy == policy


def test_profile_transition_starting_during_settings_wait_still_blocks_change(engine, monkeypatch):
    active = [False]
    monkeypatch.setattr(engine, "_profile_transition_active", lambda: active[0])
    generation = engine.http.solana_generation

    async def exercise():
        await engine._event_lock.acquire()
        task = asyncio.create_task(engine.configure_providers(engine.provider_configuration, {}))
        await asyncio.sleep(0)
        active[0] = True
        engine._event_lock.release()
        with pytest.raises(ValueError, match="profile transition"):
            await task

    asyncio.run(exercise())
    assert engine.http.solana_generation == generation


def test_change_during_fallback_does_not_apply_old_result():
    async def exercise():
        provider = HttpProviders(
            SimpleNamespace(acquire=AsyncMock(return_value=True)),
            solana_http="https://old.invalid",
            solana_fallback_http="https://fallback.invalid",
            jupiter_base="https://unused.invalid",
        )
        calls = []

        def response(request):
            calls.append(request.url.host)
            if len(calls) == 1:
                return httpx.Response(503)
            provider.configure_solana(
                "https://new.invalid", fallback_http_url="https://new.invalid"
            )
            return httpx.Response(200, json={"result": {}})

        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        assert await provider._solana_rpc_response({}) is None
        assert calls == ["old.invalid", "fallback.invalid"]
        assert provider.solana_fallback_http is None
        assert not any(provider._solana_unavailable_until.values())
        await provider.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("path", ["learning", "watchdog", "candidate"])
@pytest.mark.parametrize(
    "during_lock_wait,no_result", [(False, False), (True, False), (False, True)]
)
def test_provider_change_before_application_is_a_discard(
    engine, monkeypatch, path, during_lock_wait, no_result
):
    state, response, *_ = public_config_route("pump_curve")
    engine.demo_mode = False
    engine.features.tokens[state.mint] = state
    monkeypatch.setattr(engine, "_learning_reserve_blocked_reason", lambda: None)
    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", lambda *a, **k: [state.mint])
    target = {"mint": state.mint, "addresses": [state.mint], "minimum_slot": 0}
    monkeypatch.setattr(engine, "_position_watchdog_targets", lambda: ([target], [], 0))
    monkeypatch.setattr(
        engine, "_position_watchdog_batches", lambda _: [([target], [state.mint], 0)]
    )
    monkeypatch.setattr(engine, "_candidate_verification_targets", lambda *a: [target])
    for method in (
        "_apply_learning_reserve_result",
        "_apply_position_watchdog_result",
        "_apply_candidate_verification_result",
    ):
        monkeypatch.setattr(engine, method, lambda *a: pytest.fail("old result was applied"))

    async def exercise():
        fetched, release = asyncio.Event(), asyncio.Event()

        async def fetch(*_a, **_k):
            if during_lock_wait:
                await engine._event_lock.acquire()
                fetched.set()
                await release.wait()
            else:
                engine.http.configure_solana("https://new.invalid")
            return None if no_result else response

        monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
        operation = {
            "learning": engine._learning_reserve_tick,
            "watchdog": lambda: engine._position_watchdog_tick(datetime.now(UTC)),
            "candidate": lambda: engine._verify_candidate_accounts(datetime.now(UTC), set()),
        }[path]
        task = asyncio.create_task(operation())
        if during_lock_wait:
            await fetched.wait()
            release.set()
            await asyncio.sleep(0)
            assert not task.done()
            engine.http.configure_solana("https://new.invalid")
            engine._event_lock.release()
        await task

    asyncio.run(exercise())
    if path == "learning":
        status = engine._learning_refresh_status
        assert status["discarded_by_reason"]["context_changed"] == 1
        assert status["deferred"]["context_changed"] == 1
        assert status["accepted_routes"] == status["checkpoint_updates"] == 0
