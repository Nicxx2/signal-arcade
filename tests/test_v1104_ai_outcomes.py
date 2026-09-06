from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from signal_arcade.ai_lab import AiDecisionLab
from signal_arcade.database import Database
from signal_arcade.intelligence.reserve_refresh import validated_learning_state
from test_ai_lab import FakeHttp, _decision
from test_v1104_refresh import route_fixture


@pytest.mark.parametrize("route", ["fresh", "stale", "empty_vault"])
def test_critic_outcomes_preserve_fee_context_and_require_an_executable_route(settings, route):
    database = Database(settings.database_path)
    lab = AiDecisionLab(
        database,
        FakeHttp(),
        settings,
        select_model=lambda _: None,
        configuration_fingerprint=lambda: "config-test",
    )
    state, result, decoder, now = route_fixture()
    decision = _decision(now).model_copy(update={"mint": state.mint})
    state = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)

    async def assess():
        await lab.refresh_models()
        seed = lab._prepare_outcome(decision, state)
        assert seed is not None
        return await lab._assess(decision, seed, applied=False, timeout_seconds=1)

    assessment = asyncio.run(assess())
    assert assessment.checkpoint_network_fee_lamports == (
        settings.network_fee_lamports + settings.priority_fee_lamports
    )
    lab._track_pending(assessment)
    at = now + timedelta(minutes=5)
    if route != "stale":
        state.last_reserve_at = at
    if route == "empty_vault":
        state.real_quote_reserves = 0
    settings.network_fee_lamports = 10**12  # Cannot change an already frozen assessment.
    changed = lab.observe_market(state, at)
    if route == "stale":
        assert changed == 0
        assert lab.has_pending_outcome(state.mint)
        assert lab.expire_outcomes(at + timedelta(seconds=91)) == 1
    else:
        assert changed == 1
        saved = database.list_ai_assessments()[0]
        if route == "fresh":
            assert saved.outcome_net_return is not None
            assert saved.outcome_route_snapshot["slot"] == 101
        else:
            assert saved.outcome_net_return is None
            assert saved.outcome_missing_reason == "executable_exit_quote_unavailable"
    database.close()
