"""Current public shared configs through durable learning and position refresh."""

import asyncio
import base64
import copy
import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter

import pytest
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.intelligence.reserve_refresh import validated_learning_state
from signal_arcade.models import LearningMode, Position
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.paper.curve_math import quote_sell
from test_configurable_reserve_fees import configured_route
from test_holder_rewards import CAPTURE as HOLDER_GLOBAL
from test_learning import make_decision, make_state, policy_episode_for
from test_public_reserve_accounts import CAPTURE


def public_config_route(venue, seed=43):
    state, response, decoder, now = configured_route(venue, seed=seed)
    for item in CAPTURE["accounts"]:
        if item["venue"] == venue:
            response["accounts"][item["address"]] = {
                "owner": item["owner"],
                "executable": item["executable"],
                "raw": base64.b64decode(item["data_base64"], validate=True),
            }
    if venue == "pump_curve":
        response["accounts"][HOLDER_GLOBAL["address"]] = {
            "owner": HOLDER_GLOBAL["owner"],
            "executable": False,
            "raw": base64.b64decode(HOLDER_GLOBAL["data_base64"], validate=True),
        }
    route = state.curve_address if venue == "pump_curve" else state.pool_address
    response["accounts"][route]["raw"] += b"\x01"
    return state, response, decoder, now


@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.parametrize("batch_size", [5, 10])
def test_reviewed_route_batch_preserves_lanes_deadlines_and_restart(settings, expired, batch_size):
    engine = Orchestrator(settings)
    fixtures = [
        public_config_route("pump_curve" if seed % 2 else "pump_swap", seed)
        for seed in range(1, batch_size + 1)
    ]
    states = {s.mint: s for s, _, _, _ in fixtures}
    now = fixtures[-1][3]
    response = {
        "slot": 101,
        "accounts": {
            address: account
            for _, r, _, _ in fixtures
            for address, account in r["accounts"].items()
        },
    }
    engine.features.tokens.update(states)
    original_states = copy.deepcopy(states)
    try:
        for state in states.values():
            decision = make_decision(now - timedelta(seconds=391 if expired else 301), state.mint)
            decision.configuration_fingerprint = engine.learning.configuration_fingerprint()
            assert engine.learning.register(
                decision, make_state(state.mint), live=True, evaluation_actionable=True
            )
        if expired:
            engine.learning.expire_checkpoints(now, states=states)
        costs = {mint: engine.learning.observations[mint].entry_cost_lamports for mint in states}
        started = perf_counter()
        engine._apply_learning_reserve_result(
            {mint: copy.copy(s) for mint, s in states.items()}, states, response, now
        )
        print({"routes": batch_size, "expired": expired, "apply_seconds": perf_counter() - started})
        assert engine._learning_refresh_status["accepted_routes"] == batch_size
        saved = {}
        for state, _, decoder, _ in fixtures:
            observation = engine.learning.observations[state.mint]
            policy = policy_episode_for(engine.learning, state.mint)
            assert observation.entry_cost_lamports == costs[state.mint]
            assert policy.episode_id != observation.observation_id
            refreshed = validated_learning_state(
                state, response, decoder, requested_at=now, observed_at=now
            )
            for lane, item in (("discovery", observation), ("policy", policy)):
                checkpoint = item.checkpoints["300"]
                saved[state.mint, lane] = checkpoint.model_dump_json()
                if expired:
                    assert checkpoint.net_return is checkpoint.exit_value_lamports is None
                    assert checkpoint.missing_reason
                    continue
                assert checkpoint.route_snapshot["stored_creator_fee_bps"] == 75
                assert checkpoint.route_snapshot["proof_version"] == "learning-account-snapshot-v2"
                expected = quote_sell(
                    virtual_token_reserves=refreshed.virtual_token_reserves,
                    virtual_sol_reserves=refreshed.virtual_quote_reserves,
                    real_quote_reserves=refreshed.real_quote_reserves,
                    token_units=item.token_units,
                    fee_bps=refreshed.fee_bps,
                    fee_components=refreshed.reserve_fee_components,
                    lp_fee_bps=refreshed.reserve_lp_fee_bps,
                    network_fee_lamports=engine.learning._checkpoint_network_fee(item),
                )
                assert checkpoint.exit_value_lamports == expected.wallet_sol_lamports
        updates = engine._learning_refresh_status["checkpoint_updates"]
        response["slot"] = 102
        engine._apply_learning_reserve_result(
            {mint: copy.copy(s) for mint, s in states.items()}, states, response, now
        )
        assert engine._learning_refresh_status["checkpoint_updates"] == updates
        restarted = LearningEngine(engine.database, settings)
        for mint in states:
            assert (
                restarted.observations[mint].checkpoints["300"].model_dump_json()
                == saved[mint, "discovery"]
            )
            assert (
                policy_episode_for(restarted, mint).checkpoints["300"].model_dump_json()
                == saved[mint, "policy"]
            )
        assert engine.features.tokens == original_states
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("batch_size", [5, 10])
def test_unreviewed_public_global_blocks_only_curve_collection(settings, batch_size):
    engine = Orchestrator(settings)
    capture = json.loads(
        (Path(__file__).parent / "fixtures" / "pump_global_unreviewed_20260912.json").read_text()
    )
    fixtures = [
        public_config_route("pump_curve" if seed % 2 else "pump_swap", seed)
        for seed in range(1, batch_size + 1)
    ]
    states = {s.mint: s for s, _, _, _ in fixtures}
    now = fixtures[0][3]
    response = {
        "slot": 101,
        "accounts": {
            address: account
            for _, result, _, _ in fixtures
            for address, account in result["accounts"].items()
        },
    }
    response["accounts"][capture["address"]] = {
        "owner": capture["owner"],
        "executable": False,
        "raw": base64.b64decode(capture["data_base64"], validate=True) + b"\x01",
    }
    engine.features.tokens.update(states)
    original = copy.deepcopy(states)
    try:
        for state in states.values():
            assert engine.learning.register(
                make_decision(now - timedelta(seconds=301), state.mint),
                make_state(state.mint),
                live=True,
                evaluation_actionable=True,
            )
        engine._apply_learning_reserve_result(
            {mint: copy.copy(state) for mint, state in states.items()}, states, response, now
        )
        assert engine._learning_refresh_status["accepted_routes"] == batch_size // 2
        assert engine._learning_refresh_status["rejected"]["unreviewed_account_extension"] == (
            batch_size - batch_size // 2
        )
        for mint, state in states.items():
            for item in (
                engine.learning.observations[mint],
                policy_episode_for(engine.learning, mint),
            ):
                assert ("300" in item.checkpoints) == (state.venue == "pump_swap")
        assert engine.features.tokens == original
        health = engine._reserve_validation.status(learning=True, watchdog=False)["components"]
        assert health[0]["layout"]["unreviewed_bytes"] == 1
        assert health[1]["state"] == "verified"
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
def test_watchdog_uses_current_fees_with_learning_off_and_rejects_stale_and_unknown(
    settings, venue
):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    engine.learning.mode = LearningMode.OFF
    state, response, decoder, now = public_config_route(venue)
    engine.features.tokens[state.mint] = state
    engine.broker.positions[state.mint] = Position(
        position_id="current-fee-held",
        mint=state.mint,
        symbol="TEST",
        token_units=10**12,
        entry_cost_lamports=30_000_000,
        book_value_lamports=30_000_000,
        opened_at=now - timedelta(minutes=2),
        entry_fill_id="entry",
        last_marked_at=now - timedelta(minutes=1),
    )
    targets = engine._position_watchdog_targets()[0]
    try:
        expected = validated_learning_state(
            state, response, decoder, requested_at=now, observed_at=now
        )
        _, refreshed, _ = engine._apply_position_watchdog_result(targets, response, now)
        assert refreshed == {state.mint}
        assert state.reserve_fee_components == expected.reserve_fee_components
        assert state.reserve_audit["stored_creator_fee_bps"] == 75
        assert not engine.learning.observations
        position = engine.broker.positions[state.mint]
        assert position.mark_is_executable
        before = copy.deepcopy(state)
        for failure in ("stale", "unknown"):
            bad = copy.deepcopy(response)
            if failure == "stale":
                bad["slot"] = 99
            else:
                bad["slot"] = 102
                for item in CAPTURE["accounts"]:
                    if item["venue"] == venue:
                        bad["accounts"][item["address"]]["raw"] += b"\x01"
            _, changed, _ = engine._apply_position_watchdog_result(targets, bad, now)
            assert not changed
            assert state == before
            assert state.mint in engine.broker.positions
            assert not engine._position_route_probes[state.mint]["verified"]
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
