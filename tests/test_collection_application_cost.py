"""Compare equal routes through real validation and persistence, without a live workload."""

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from time import perf_counter, process_time

import pytest
from signal_arcade.orchestrator import Orchestrator, _detailed_to_thread
from test_learning import make_decision, make_state, policy_episode_for
from test_reserve_contract_integration import public_config_route


@pytest.mark.parametrize("measured_first", [False, True])
def test_equal_cohort_batch_options_preserve_values_and_measure_application(
    settings, monkeypatch, measured_first
):
    import signal_arcade.orchestrator as orchestration

    fixtures = [
        public_config_route("pump_curve" if seed % 2 else "pump_swap", seed)
        for seed in range(1, 21)
    ]
    now = datetime.now(UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(orchestration, "datetime", FixedDateTime)
    values = []
    cases = [
        (batch, measured)
        for batch in (5, 10, 20)
        for measured in (measured_first, not measured_first)
    ]
    for batch, measured in cases:
        engine = Orchestrator(
            settings.model_copy(update={"data_dir": settings.data_dir / f"{batch}-{measured}"})
        )
        engine.diagnostics.enabled = measured
        states = {s.mint: copy.deepcopy(s) for s, _, _, _ in fixtures}
        engine.features.tokens.update(states)
        original = copy.deepcopy(states)
        durations = []
        cpu_durations = []
        try:
            for mint in states:
                decision = make_decision(now - timedelta(seconds=301), mint)
                decision.configuration_fingerprint = engine.learning.configuration_fingerprint()
                assert engine.learning.register(
                    decision, make_state(mint), live=True, evaluation_actionable=True
                )
            for offset in range(0, len(fixtures), batch):
                selected = fixtures[offset : offset + batch]
                response = {
                    "slot": 101,
                    "accounts": {
                        address: account
                        for _, result, _, _ in selected
                        for address, account in result["accounts"].items()
                    },
                }
                assert len(response["accounts"]) <= 100
                snapshots = {s.mint: copy.copy(states[s.mint]) for s, _, _, _ in selected}
                started = perf_counter()
                cpu_started = process_time()
                asyncio.run(
                    _detailed_to_thread(
                        engine.diagnostics,
                        "rpc",
                        engine._apply_learning_reserve_result,
                        snapshots,
                        states,
                        response,
                        now,
                    )
                )
                durations.append(perf_counter() - started)
                cpu_durations.append(process_time() - cpu_started)
            assert engine.features.tokens == original
            assert engine._learning_refresh_status["accepted_routes"] == 20
            if measured:
                detail = engine.diagnostics.work_detail_since_boot["rpc"]
                assert detail["rpc_validate"][0] == detail["rpc_observe"][0] == 20
                assert detail["rpc_dispatch"][0] == 20 // batch
                assert detail["checkpoint_persist"][0] == 40
            else:
                assert not engine.diagnostics.work_detail_since_boot
            values.append(
                {
                    (mint, lane): item.checkpoints["300"].model_dump(mode="json")
                    for mint in states
                    for lane, item in (
                        ("discovery", engine.learning.observations[mint]),
                        ("policy", policy_episode_for(engine.learning, mint)),
                    )
                }
            )
            print(
                {
                    "batch": batch,
                    "measured": measured,
                    "routes": 20,
                    "apply_seconds": durations,
                    "apply_cpu_seconds": cpu_durations,
                    "max_apply_call_seconds": max(durations),
                    "detail": engine.diagnostics.work_detail_since_boot,
                }
            )
        finally:
            asyncio.run(engine.http.close())
            engine.database.close()
    assert all(value == values[0] for value in values)
