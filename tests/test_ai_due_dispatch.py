"""Only provable pre-horizon no-ops may skip optional AI outcome dispatch."""

# ruff: noqa: F811 -- shared engine fixture

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from signal_arcade.ai_lab import AiDecisionLab
from signal_arcade.database import Database
from signal_arcade.intelligence.reserve_refresh import validated_learning_state
from signal_arcade.models import AiDecisionMode, EventKind, MarketEvent
from test_ai_lab import FakeHttp, _decision
from test_probe_retention import engine  # noqa: F401
from test_v1104_refresh import route_fixture


@pytest.fixture
def outcome(settings):
    database = Database(settings.database_path)
    lab = AiDecisionLab(
        database,
        FakeHttp(),
        settings,
        select_model=lambda _: None,
        configuration_fingerprint=lambda: "test",
    )
    state, result, decoder, now = route_fixture()
    state = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)

    async def assess():
        await lab.refresh_models()
        decision = _decision(now).model_copy(update={"mint": state.mint})
        return await lab._assess(
            decision, lab._prepare_outcome(decision, state), applied=False, timeout_seconds=1
        )

    assessment = asyncio.run(assess())
    assert assessment is not None
    database.save_ai_assessment(assessment)
    lab._track_pending(assessment)
    try:
        yield lab, state, assessment, now
    finally:
        database.close()


@pytest.mark.parametrize(
    "case",
    [
        "before",
        "due",
        "grace",
        "expired",
        "stale",
        "empty",
        "missing_fee",
        "zero_fee",
        "missing_seed",
        "no_clock",
        "save_error",
    ],
)
def test_dispatch_filter_matches_real_outcomes_fees_failures_and_pending_state(
    outcome, monkeypatch, case
):
    lab, state, assessment, now = outcome
    at = now + timedelta(seconds=300)
    if case == "before":
        at -= timedelta(microseconds=1)
    elif case == "grace":
        at += timedelta(seconds=90)
    elif case == "expired":
        at += timedelta(seconds=90, microseconds=1)
    state.last_reserve_at = now if case == "stale" else at
    if case == "empty":
        state.real_quote_reserves = 0
    changes = {
        "missing_fee": {"checkpoint_network_fee_lamports": None},
        "zero_fee": {"checkpoint_network_fee_lamports": 0, "fee_bps": 0},
        "missing_seed": {"token_units": None},
        "no_clock": {"outcome_due_at": None},
    }
    assessment = assessment.model_copy(update=changes.get(case, {}))
    original_save = lab.database.save_ai_assessment
    results = []
    for filtered in (False, True):
        lab.pending_outcomes = {state.mint: [assessment]}
        lab.qualification_cache = None
        writes = []

        def save(value, writes=writes):
            if case == "save_error":
                raise RuntimeError("commit failed")
            original_save(value)
            writes.append(value.model_dump(mode="json"))

        monkeypatch.setattr(lab.database, "save_ai_assessment", save)
        error = None
        changed = None
        try:
            changed = (
                lab.observe_market(state, at)
                if not filtered or lab.has_due_outcome(state.mint, at)
                else 0
            )
        except RuntimeError as exc:
            error = str(exc)
        results.append(
            (
                changed,
                error,
                writes,
                {
                    mint: [a.model_dump(mode="json") for a in items]
                    for mint, items in lab.pending_outcomes.items()
                },
            )
        )
    assert results[0] == results[1]
    if case == "due":
        assert results[1][2][0]["outcome_net_return"] < 0  # Negative evidence remains usable.
    if case in {"before", "stale", "no_clock", "save_error"}:
        assert lab.has_pending_outcome(state.mint)


def test_multiple_assessments_inflight_result_and_incomparable_clocks_are_conservative(outcome):
    lab, state, assessment, now = outcome
    due = now + timedelta(seconds=300)
    future = assessment.model_copy(
        update={"assessment_id": "future", "outcome_due_at": due + timedelta(seconds=1)}
    )
    lab.pending_outcomes[state.mint] = [future, assessment]
    assert lab.has_due_outcome(state.mint, due)
    assert not lab.has_due_outcome(state.mint, due - timedelta(microseconds=1))
    lab.queued_mints.add(state.mint)
    assert lab.has_due_outcome(state.mint, now)
    lab.queued_mints.clear()
    assert lab.has_due_outcome(state.mint, now.replace(tzinfo=None))
    assert lab.has_pending_outcome(state.mint) and state.mint in lab.tracked_mints
    assert not lab.has_due_outcome("absent", due)


def test_restart_and_mode_change_preserve_future_outcomes(outcome):
    lab, state, assessment, now = outcome
    restored = AiDecisionLab(
        lab.database,
        FakeHttp(),
        lab.settings,
        select_model=lambda _: None,
        configuration_fingerprint=lambda: "test",
    )
    for mode in AiDecisionMode:
        restored.mode = mode
        assert restored.has_pending_outcome(state.mint)
        assert not restored.has_due_outcome(state.mint, now)
        assert restored.has_due_outcome(state.mint, assessment.outcome_due_at)
    assert restored.expire_outcomes(assessment.outcome_due_at + timedelta(seconds=90)) == 0
    assert (
        restored.expire_outcomes(assessment.outcome_due_at + timedelta(seconds=90, microseconds=1))
        == 1
    )


@pytest.mark.parametrize("mode", list(AiDecisionMode))
def test_real_dispatch_skips_future_calls_but_keeps_priority_and_first_due_tick(
    engine, monkeypatch, mode
):  # noqa: F811
    state, _result, _decoder, now = route_fixture()
    due = now + timedelta(seconds=300)
    engine.running = False
    engine.ai_lab.mode = mode
    engine.ai_lab.pending_outcomes[state.mint] = [SimpleNamespace(outcome_due_at=due)]
    monkeypatch.setattr(engine.features, "apply", lambda _: state)
    monkeypatch.setattr(engine, "_event_regresses_verified_route", lambda _: False)
    monkeypatch.setattr(engine, "_accept_event_order", lambda *_: True)
    called = []
    monkeypatch.setattr(engine.ai_lab, "observe_market", lambda s, at: called.append(at) or 0)

    async def run():
        yielded = []
        for i in range(100):
            event = MarketEvent(
                event_id=str(i),
                source="test",
                kind=EventKind.TRADE,
                mint=state.mint,
                received_at=now + timedelta(seconds=i),
            )
            assert engine._event_priority(event) == 0
            assert not engine._ignore_untracked_trade(event)
            asyncio.get_running_loop().call_soon(yielded.append, i)
            await engine._handle_persisted_event(event)
            assert yielded[-1] == i  # A future-only burst still lets other tasks run.
        assert not called and state.mint in engine.ai_lab.tracked_mints
        event = event.model_copy(update={"event_id": "due", "received_at": due})
        await engine._handle_persisted_event(event)
        assert called == [due]
        assert engine.diagnostics.ai_dispatch_since_boot == {"dispatch": 1, "not_due": 100}

    asyncio.run(run())


def test_inflight_result_keeps_the_existing_dispatch_await_boundary(engine, monkeypatch):  # noqa: F811
    state, _result, _decoder, now = route_fixture()
    lab = engine.ai_lab
    future = SimpleNamespace(outcome_due_at=now + timedelta(seconds=300))
    lab.pending_outcomes[state.mint] = [future]
    lab.queued_mints.add(state.mint)
    engine.running = False
    monkeypatch.setattr(engine.features, "apply", lambda _: state)
    monkeypatch.setattr(engine, "_event_regresses_verified_route", lambda _: False)
    monkeypatch.setattr(engine, "_accept_event_order", lambda *_: True)
    called = []

    async def dispatch(recorder, phase, function, *args, **kwargs):
        await asyncio.sleep(0)
        lab.pending_outcomes[state.mint].append(SimpleNamespace(outcome_due_at=now))
        lab.queued_mints.discard(state.mint)
        return function(*args, **kwargs)

    monkeypatch.setattr("signal_arcade.orchestrator._timed_to_thread", dispatch)
    monkeypatch.setattr(
        lab, "observe_market", lambda s, at: called.append(len(lab.pending_outcomes[s.mint])) or 0
    )
    event = MarketEvent(
        event_id="inflight", source="test", kind=EventKind.TRADE, mint=state.mint, received_at=now
    )
    asyncio.run(engine._handle_persisted_event(event))
    assert called == [2]
