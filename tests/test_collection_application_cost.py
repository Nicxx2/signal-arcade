"""Compare equal routes through real validation and persistence, without a live workload."""

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from time import perf_counter

from signal_arcade.orchestrator import Orchestrator
from test_learning import make_decision, make_state, policy_episode_for
from test_reserve_contract_integration import public_config_route


def test_equal_cohort_batch_options_preserve_values_and_measure_application(settings, monkeypatch):
    import signal_arcade.orchestrator as orchestration

    fixtures = [
        public_config_route("pump_curve" if seed % 2 else "pump_swap", seed)
        for seed in range(1, 11)
    ]
    now = datetime.now(UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(orchestration, "datetime", FixedDateTime)
    values = []
    for batch in (5, 10):
        engine = Orchestrator(
            settings.model_copy(update={"data_dir": settings.data_dir / str(batch)})
        )
        states = {s.mint: copy.deepcopy(s) for s, _, _, _ in fixtures}
        engine.features.tokens.update(states)
        original = copy.deepcopy(states)
        durations = []
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
                engine._apply_learning_reserve_result(snapshots, states, response, now)
                durations.append(perf_counter() - started)
            assert engine.features.tokens == original
            assert engine._learning_refresh_status["accepted_routes"] == 10
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
                    "routes": 10,
                    "apply_seconds": durations,
                    "max_uninterrupted_apply_seconds": max(durations),
                }
            )
        finally:
            asyncio.run(engine.http.close())
            engine.database.close()
    assert values[0] == values[1]
