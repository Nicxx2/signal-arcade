"""Skip idle learning handoffs without changing any due evidence or held-position work."""

import asyncio
import copy
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.intelligence.learning import LEARNING_HORIZONS_SECONDS, LearningEngine
from signal_arcade.models import (
    EventKind,
    LearningCheckpoint,
    LearningEvidenceStatus,
    LearningObservationStatus,
    MarketEvent,
    Position,
)
from signal_arcade.orchestrator import Orchestrator
from test_learning import make_decision, make_state, policy_episode_for


def enrolled(settings, mint="dispatch"):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    start = datetime(2026, 9, 12, tzinfo=UTC)
    state = make_state(mint)
    state.real_quote_reserves = 30_000_000_000
    assert learner.register(
        make_decision(start, mint), state, live=True, evaluation_actionable=True
    )
    return learner, database, state, start


@pytest.mark.parametrize("lane", ["discovery", "policy"])
def test_each_horizon_keeps_exact_boundaries_and_overdue_work(settings, lane):
    learner, database, state, start = enrolled(settings)
    observation = learner.observations[state.mint]
    policy = policy_episode_for(learner, state.mint)
    try:
        assert not learner.has_due_market_work("absent", start)
        if lane == "discovery":
            policy.status = LearningEvidenceStatus.COMPLETE
            item, entered = observation, start
        else:
            observation.status = LearningObservationStatus.COMPLETE
            policy.entry_at = start + timedelta(seconds=13)
            item, entered = policy, policy.entry_at
        for horizon in LEARNING_HORIZONS_SECONDS:
            item.checkpoints = {
                str(other): LearningCheckpoint(horizon_seconds=other, observed_at=entered)
                for other in LEARNING_HORIZONS_SECONDS
                if other != horizon
            }
            assert not learner.has_due_market_work(
                state.mint, entered + timedelta(seconds=horizon, microseconds=-1)
            )
            for offset in (0, 90, 90.000001, 5000):
                assert learner.has_due_market_work(
                    state.mint, entered + timedelta(seconds=horizon + offset)
                )
        # A restored pending record with its last checkpoint already saved still needs closure.
        item.checkpoints["1200"] = LearningCheckpoint(horizon_seconds=1200, observed_at=entered)
        assert learner.has_due_market_work(state.mint, entered)
    finally:
        database.close()


def test_policy_clock_can_be_due_while_discovery_is_between_horizons(settings):
    learner, database, state, start = enrolled(settings)
    try:
        learner.observations[state.mint].checkpoints["60"] = LearningCheckpoint(
            horizon_seconds=60, observed_at=start + timedelta(seconds=60)
        )
        policy = policy_episode_for(learner, state.mint)
        policy.entry_at = start + timedelta(seconds=13)
        assert not learner.has_due_market_work(state.mint, start + timedelta(seconds=72.999999))
        assert learner.has_due_market_work(state.mint, start + timedelta(seconds=73))
        learner.observations.clear()  # A Policy-only mint must keep collecting.
        assert learner.has_due_market_work(state.mint, start + timedelta(seconds=73))
    finally:
        database.close()


@pytest.mark.parametrize("cached", [False, True])
def test_dispatch_filter_preserves_real_durable_evidence_through_restart(
    settings, tmp_path, cached
):
    results = []
    counts = []
    for filtered in (False, True):
        configured = settings.model_copy(update={"data_dir": tmp_path / str(filtered)})
        learner, database, _, start = enrolled(configured)
        states = {"dispatch": make_state("dispatch")}
        for mint in ("stale", "illiquid", "discovery-only"):
            states[mint] = make_state(mint)
            assert learner.register(
                make_decision(start, mint),
                states[mint],
                live=True,
                evaluation_actionable=mint != "discovery-only",
            )
        for mint, state in states.items():
            state.real_quote_reserves = 1 if mint == "illiquid" else 30_000_000_000
            if mint != "discovery-only":
                policy = policy_episode_for(learner, mint)
                policy.entry_at += timedelta(seconds=13)
                database.save_learning_evidence_episode(policy)
        calls = 0
        # Duplicate and backward timestamps exercise immutable completed checkpoints too.
        times = [*range(61), 60, 59, *range(61, 1310)]
        try:
            for second in times:
                if second == 650:
                    database.close()
                    database = Database(configured.database_path)
                    learner = LearningEngine(database, configured)
                now = start + timedelta(seconds=second)
                for mint, state in states.items():
                    state.last_reserve_at = (
                        start - timedelta(seconds=100) if mint == "stale" else now
                    )
                    state.last_event_at = now
                    if learner.has_pending_mint(mint) and (
                        not filtered or learner.has_due_market_work(mint, now)
                    ):
                        calls += 1
                        learner.observe_market(state, now, live=True, cached=cached)
            # Compare saved records after reload, including fees, attempts, every horizon,
            # Policy identity, completion and receipts, not just summary counts.
            restored = LearningEngine(database, configured)
            results.append(
                (
                    {m: o.model_dump(mode="json") for m, o in restored.observations.items()},
                    {k: e.model_dump(mode="json") for k, e in restored.evidence_episodes.items()},
                    restored._training_rows(),
                    restored._policy_identities,
                )
            )
            counts.append(calls)
            assert [row.mint for row, _ in restored._training_rows()] == ["discovery-only"]
            for item in (*restored.observations.values(), *restored.evidence_episodes.values()):
                if item.mint in states:
                    assert set(item.checkpoints) == {str(h) for h in LEARNING_HORIZONS_SECONDS}
            assert restored.observations["dispatch"].checkpoints["300"].net_return is not None
            assert restored.observations["illiquid"].checkpoints["300"].net_return is None
            assert restored.observations["stale"].checkpoints["300"].net_return is None
        finally:
            database.close()
    assert results[0] == results[1]
    assert counts[1] < counts[0] / 2
    print({"original_dispatches": counts[0], "due_dispatches": counts[1]})


@pytest.mark.parametrize("initial_count", [0, 2**63 - 1])
def test_non_due_learning_does_not_skip_features_or_held_position_updates(
    settings, monkeypatch, initial_count
):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    engine.running = True
    engine._learning_dispatch_counts["not_due"] = initial_count
    start = datetime.now(UTC)
    state = make_state("held")
    state.real_quote_reserves = 30_000_000_000
    engine.features.tokens[state.mint] = state
    assert engine.learning.register(
        make_decision(start, state.mint), state, live=True, evaluation_actionable=True
    )
    engine.broker.positions[state.mint] = Position(
        position_id="held",
        mint=state.mint,
        symbol="TEST",
        token_units=10**9,
        entry_cost_lamports=1_000_000,
        book_value_lamports=1_000_000,
        opened_at=start,
        entry_fill_id="entry",
    )
    observed = []
    monkeypatch.setattr(
        engine.learning, "observe_market", lambda *a, **k: pytest.fail("idle handoff")
    )
    monkeypatch.setattr(
        engine.broker,
        "on_market_state",
        lambda **kw: observed.append((kw["source_event_id"], kw["state"].last_event_id)) or [],
    )
    before = copy.deepcopy(engine.learning.observations[state.mint])

    async def run():
        for index in range(1, 21):
            assert await engine._handle_persisted_event(
                MarketEvent(
                    event_id=str(index),
                    mint=state.mint,
                    source="test",
                    kind=EventKind.TRADE,
                    received_at=start + timedelta(seconds=index),
                    payload={"is_buy": True, "sol_amount": 0.01},
                )
            )
        await engine.http.close()

    try:
        asyncio.run(run())
        assert observed == [(str(i), str(i)) for i in range(1, 21)]
        assert engine.learning.observations[state.mint] == before
        assert engine._learning_dispatch_counts == {
            "due": 0,
            "not_due": min(2**63 - 1, initial_count + 20),
        }
    finally:
        engine.database.close()


def test_wait_totals_ignore_nonfinite_values_and_keep_fixed_memory(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.observe_learning_waits(1.25, 0.5)
    for bad in (float("inf"), float("nan"), -1):
        recorder.observe_learning_waits(bad, bad)
    assert recorder.learning_waits_since_boot == {"dispatch": 1.25, "resume": 0.5}
    recorder.observe_learning_waits(1e20, 1e20)
    assert recorder.learning_waits_since_boot == {"dispatch": 1e12, "resume": 1e12}
    disabled = DiagnosticsRecorder(tmp_path, enabled=False)
    disabled.observe_learning_waits(3, 4)
    assert disabled.learning_waits_since_boot == {"dispatch": 0.0, "resume": 0.0}
    assert not recorder.phases and not recorder.events and not recorder.queue


def test_real_event_handler_resumes_each_lane_and_keeps_ai_and_order_updates(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.running = True
    engine.demo_mode = False
    start = datetime.now(UTC)
    state = make_state("separate-clocks")
    state.real_quote_reserves = 30_000_000_000
    engine.features.tokens[state.mint] = state
    assert engine.learning.register(
        make_decision(start, state.mint), state, live=True, evaluation_actionable=True
    )
    policy = policy_episode_for(engine.learning, state.mint)
    policy.entry_at += timedelta(seconds=13)
    ai_calls, broker_calls, learning_calls = [], [], []
    original = engine.learning.observe_market

    def observe(token, now, **kwargs):
        learning_calls.append(now)
        return original(token, now, **kwargs)

    monkeypatch.setattr(engine.learning, "observe_market", observe)
    # A pending order, without a position, must also retain the broker update path.
    monkeypatch.setattr(engine.broker, "has_pending_for", lambda mint: mint == state.mint)
    monkeypatch.setattr(engine.ai_lab, "has_pending_outcome", lambda mint: mint == state.mint)
    monkeypatch.setattr(
        engine.ai_lab, "observe_market", lambda token, now: ai_calls.append(now) or 0
    )
    monkeypatch.setattr(
        engine.broker, "on_market_state", lambda **kw: broker_calls.append(kw["now"]) or []
    )
    times = [start + timedelta(seconds=second) for second in (59, 60, 61, 72, 73, 74)]

    async def run():
        for index, now in enumerate(times):
            assert await engine._handle_persisted_event(
                MarketEvent(
                    event_id=str(index),
                    mint=state.mint,
                    source="test",
                    kind=EventKind.TRADE,
                    received_at=now,
                    payload={"is_buy": True, "sol_amount": 0.01},
                )
            )
        await engine.http.close()

    try:
        asyncio.run(run())
        assert learning_calls == [times[1], times[4]]
        assert ai_calls == broker_calls == times
        assert engine._learning_dispatch_counts == {"due": 2, "not_due": 4}
        restored = LearningEngine(engine.database, settings)
        observation = restored.observations[state.mint]
        policy = policy_episode_for(restored, state.mint)
        for item, now in ((observation, times[1]), (policy, times[4])):
            assert list(item.checkpoints) == ["60"]
            assert item.checkpoints["60"].observed_at == now
            assert item.checkpoints["60"].net_return is not None
        assert not restored._training_rows()  # The Policy twin stays out of training.
    finally:
        engine.database.close()


def test_later_indexed_policy_episode_is_not_hidden_by_finished_or_future_episodes(settings):
    learner, database, state, start = enrolled(settings)
    try:
        learner.observations[state.mint].status = LearningObservationStatus.COMPLETE
        first = policy_episode_for(learner, state.mint)
        later = first.model_copy(deep=True, update={"episode_id": "second-policy"})
        later.entry_at = start + timedelta(seconds=13)
        learner.remember_committed_evidence(later)
        first.entry_at = start + timedelta(seconds=1000)
        assert learner.has_due_market_work(state.mint, start + timedelta(seconds=73))
        first.status = LearningEvidenceStatus.COMPLETE
        assert learner.has_due_market_work(state.mint, start + timedelta(seconds=73))
        learner.evidence_episodes[later.episode_id].status = LearningEvidenceStatus.COMPLETE
        assert not learner.has_due_market_work(state.mint, start + timedelta(seconds=73))
    finally:
        database.close()
