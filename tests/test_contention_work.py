"""Inner measurements preserve candidate results and remain local to joined workers."""

# ruff: noqa: F811 -- shared fixture

import asyncio

import pytest
from signal_arcade.orchestrator import _detailed_to_thread, _timed_to_thread
from signal_arcade.strategy import strategy_fingerprint_payload
from signal_arcade.work_timing import WORK_DETAIL, measure_work
from test_learning import make_decision
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("enabled", [False, True])
def test_candidate_inner_measurements_preserve_real_decision(engine, enabled, monkeypatch):
    from datetime import UTC, datetime

    engine.diagnostics.enabled = enabled
    monkeypatch.setattr(engine, "_active_strategy_versions", strategy_fingerprint_payload)
    snapshot = make_decision(datetime.now(UTC), "candidate-profile").feature_snapshot
    expected, expected_actionable = engine._prepare_baseline_decision(snapshot, 100.0)
    actual, actionable = asyncio.run(
        _timed_to_thread(
            engine.diagnostics,
            "event_candidate",
            engine._prepare_baseline_decision,
            snapshot,
            100.0,
        )
    )
    assert actual.model_dump(exclude={"decision_id", "created_at"}) == expected.model_dump(
        exclude={"decision_id", "created_at"}
    )
    assert actionable == expected_actionable
    assert WORK_DETAIL.get() is None
    detail = engine.diagnostics.work_detail_since_boot
    if enabled:
        assert detail["candidate"]["candidate_reference"][0] == 1
        assert detail["candidate"]["candidate_policy"][0] == 1
        assert detail["candidate"]["candidate_sizing"][0] == 1
    else:
        assert not detail


@pytest.mark.parametrize("phase", ["event_learning", "heartbeat", "rpc"])
@pytest.mark.parametrize("failure", [False, True])
def test_governance_detail_is_exported_once_after_worker_finishes(engine, phase, failure):
    marker = object()

    def run():
        with measure_work("govern_health"):
            assert WORK_DETAIL.get() is not None
            if failure:
                raise ValueError("governance fixture")
            return marker

    async def exercise():
        function = _detailed_to_thread if phase == "rpc" else _timed_to_thread
        return await function(engine.diagnostics, phase, run)

    if failure:
        with pytest.raises(ValueError, match="governance fixture"):
            asyncio.run(exercise())
    else:
        assert asyncio.run(exercise()) is marker
    assert engine.diagnostics.work_detail_since_boot["governance"]["govern_health"][0] == 1
    assert WORK_DETAIL.get() is None
