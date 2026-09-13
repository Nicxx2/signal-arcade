from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from signal_arcade import orchestrator
from signal_arcade.coach import COACH_INFERENCE_TIMEOUT_SECONDS
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import ExitAssessment, Position, PositionMarketStatus, RiskMode
from signal_arcade.orchestrator import Orchestrator
from test_coach import _observation
from test_coach_pressure import coach_for
from test_exit_policy import features as exit_features

NOW = datetime(2026, 9, 12, 21, 0, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


@pytest.fixture
def coach_runtime(settings, monkeypatch):
    engine = Orchestrator(settings)
    monkeypatch.setattr(orchestrator, "datetime", Clock)
    engine.demo_mode = False
    engine.started_at = NOW - timedelta(minutes=2)
    engine.broker.season_id = "coach-hold-season"
    try:
        yield engine
    finally:
        engine.database.close()


def held(engine, *, age=660, assessment_age=1):
    evaluated = NOW - timedelta(seconds=assessment_age)
    limits = engine.broker.risk_limits(engine.risk_mode)
    return Position(
        position_id="held",
        mint="held",
        symbol="HELD",
        token_units=100,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=NOW - timedelta(seconds=age),
        entry_fill_id="fill-held",
        last_marked_at=evaluated,
        mark_is_stale=False,
        mark_is_executable=True,
        market_status="active",
        exit_assessment=ExitAssessment(
            evaluated_at=evaluated,
            action="hold",
            reason="adaptive_extension",
            support_score=0.9,
            pnl_fraction=0.05,
            peak_return_fraction=0.06,
            drawdown_from_peak_fraction=0.01,
            age_seconds=age - assessment_age,
            soft_hold_seconds=limits.max_hold_seconds,
            hard_hold_seconds=limits.hard_max_hold_seconds,
            strategy_season_id=engine.broker.season_id,
        ),
    )


def admission(engine, position):
    engine.broker.positions[position.mint] = position
    return engine._coach_can_run()


@pytest.mark.parametrize("mode", list(RiskMode))
def test_fresh_adaptive_hold_allows_research_after_normal_review(coach_runtime, mode):
    engine = coach_runtime
    engine.risk_mode = mode
    limits = engine.broker.risk_limits(mode)
    assert admission(engine, held(engine, age=limits.max_hold_seconds + 60)) == (True, None)


@pytest.mark.parametrize("mode", list(RiskMode))
def test_real_broker_hold_assessment_allows_coach_until_exit_becomes_due(coach_runtime, mode):
    engine = coach_runtime
    engine.risk_mode = mode
    limits = engine.broker.risk_limits(mode)
    position = held(engine, age=limits.max_hold_seconds + 60)
    position.exit_assessment = None
    position.last_mark_lamports = 110
    position.peak_mark_lamports = 110
    position.unrealized_pnl_lamports = 10
    assert admission(engine, position) == (False, "protecting_open_positions")
    state = TokenState(mint=position.mint)
    features = exit_features(NOW).model_copy(update={"mint": position.mint})

    engine.broker._schedule_exit_if_needed(state, features, NOW, mode)

    assert position.exit_assessment.action == "hold"
    assert position.exit_assessment.reason == "adaptive_extension"
    assert not engine.broker.pending
    before_admission = position.model_dump(mode="json")
    assert engine._coach_can_run() == (True, None)
    assert position.model_dump(mode="json") == before_admission

    features.hard_flags = ["creator_sold_recently"]
    engine.broker._schedule_exit_if_needed(state, features, NOW, mode)

    assert position.exit_assessment.action == "exit"
    assert position.exit_assessment.reason == "creator_sell_exit"
    assert len(engine.broker.pending) == 1
    assert engine._coach_can_run() == (False, "protecting_open_positions")


@pytest.mark.parametrize("age,allowed", [(569, True), (570, False), (600, False), (601, True)])
def test_normal_review_still_runs_before_research_exception(coach_runtime, age, allowed):
    assert admission(coach_runtime, held(coach_runtime, age=age))[0] is allowed


@pytest.mark.parametrize("remaining,allowed", [(106, True), (105, False), (104, False), (0, False)])
def test_extended_hold_leaves_full_inference_budget_before_hard_exit(
    coach_runtime, remaining, allowed
):
    assert COACH_INFERENCE_TIMEOUT_SECONDS == 75
    limits = coach_runtime.broker.risk_limits(coach_runtime.risk_mode)
    position = held(coach_runtime, age=limits.hard_max_hold_seconds - remaining)
    assert admission(coach_runtime, position)[0] is allowed


@pytest.mark.parametrize(
    "updates",
    [
        {"action": "exit"},
        {"action": "wait"},
        {"reason": "evidence_supports_hold"},
        {"policy_version": "old-policy"},
        {"strategy_season_id": "other-season"},
        {"strategy_season_id": None},
        {"evaluated_at": NOW + timedelta(microseconds=1)},
        {"evaluated_at": NOW.replace(tzinfo=None)},
        {"evaluated_at": "broken"},
        {"age_seconds": float("nan")},
        {"age_seconds": None},
        {"age_seconds": 10},
        {"soft_hold_seconds": None},
        {"soft_hold_seconds": 1200},
        {"hard_hold_seconds": 3600},
        {"support_score": float("nan")},
        {"support_score": None},
        {"support_score": 0.1},
    ],
)
def test_invalid_or_non_hold_assessment_cannot_grant_exception(coach_runtime, updates):
    position = held(coach_runtime)
    position.exit_assessment = position.exit_assessment.model_copy(update=updates)
    assert admission(coach_runtime, position) == (False, "protecting_open_positions")


@pytest.mark.parametrize("assessment_age,allowed", [(30, True), (30.000001, False), (90, False)])
def test_assessment_freshness_has_its_own_bounded_window(coach_runtime, assessment_age, allowed):
    assert (
        admission(coach_runtime, held(coach_runtime, assessment_age=assessment_age))[0] is allowed
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"exit_assessment": None},
        {"mark_is_stale": True},
        {"mark_is_executable": False},
        {"mark_blockers": ["exit_route_unavailable"]},
        {"last_marked_at": None},
        {"last_marked_at": NOW + timedelta(seconds=1)},
        {"last_marked_at": NOW - timedelta(seconds=91)},
        {"last_marked_at": NOW},  # A newer mark has not been assessed yet.
        {"opened_at": NOW + timedelta(seconds=1)},
    ],
)
def test_position_evidence_must_be_current_and_executable(coach_runtime, updates):
    position = held(coach_runtime).model_copy(update=updates)
    assert admission(coach_runtime, position) == (False, "protecting_open_positions")


def test_restart_requires_a_new_assessment(coach_runtime):
    position = held(coach_runtime)
    coach_runtime.started_at = NOW
    assert admission(coach_runtime, position) == (False, "protecting_open_positions")


def test_missing_start_boundary_cannot_grant_extended_hold_exception(coach_runtime):
    coach_runtime.started_at = None
    assert admission(coach_runtime, held(coach_runtime))[0] is False


@pytest.mark.parametrize("mode", list(RiskMode))
def test_current_effective_exit_limits_remain_authoritative(coach_runtime, mode):
    position = held(coach_runtime, age=800)
    coach_runtime.risk_mode = mode
    if mode == RiskMode.BALANCED:
        assert admission(coach_runtime, position)[0] is True
    else:
        # SAFE tightens the hard deadline; AGGRESSIVE has not reached its normal review.
        expected = mode == RiskMode.AGGRESSIVE
        assert admission(coach_runtime, position)[0] is expected


@pytest.mark.parametrize("guard", ["pending", "queue", "lag", "boundary", "maintenance", "fit"])
def test_extended_hold_does_not_bypass_other_work_guards(coach_runtime, monkeypatch, guard):
    engine = coach_runtime
    if guard == "pending":
        engine.broker.pending["pending"] = object()
    elif guard == "queue":
        monkeypatch.setattr(engine.event_queue, "qsize", lambda: engine.settings.event_queue_max)
    elif guard == "lag":
        engine.last_processing_lag_seconds = 1
    elif guard == "boundary":
        monkeypatch.setattr(type(engine.event_queue), "boundary_active", property(lambda _: True))
    elif guard == "maintenance":
        engine._storage_maintenance_active = True
    else:
        engine.learning._training_active = object()
    expected = "protecting_open_positions" if guard == "pending" else "protecting_market_throughput"
    assert admission(engine, held(engine)) == (False, expected)


def test_one_urgent_position_blocks_research_but_dormant_inventory_does_not(coach_runtime):
    engine = coach_runtime
    position = held(engine)
    assert admission(engine, position) == (True, None)
    urgent = held(engine, age=1770).model_copy(update={"mint": "urgent"})
    assert admission(engine, urgent) == (False, "protecting_open_positions")
    urgent.market_status = PositionMarketStatus.DORMANT
    assert engine._coach_can_run() == (True, None)


def test_admission_does_not_read_database_or_reassess_trading(coach_runtime, monkeypatch):
    engine = coach_runtime
    for owner, name in [
        (engine.database, "recent_learning_observations"),
        (engine.database, "save_position"),
        (engine.broker, "reassess_position"),
        (engine.learning, "exit_timing_selection"),
    ]:
        monkeypatch.setattr(owner, name, lambda *a, **kw: pytest.fail("admission did extra work"))
    assert admission(engine, held(engine)) == (True, None)


def test_earlier_champion_review_does_not_replace_normal_review(coach_runtime):
    position = held(coach_runtime, age=600, assessment_age=1)
    position.exit_assessment.soft_hold_seconds = 300
    assert admission(coach_runtime, position)[0] is False
    position = held(coach_runtime, age=601, assessment_age=1)
    position.exit_assessment.soft_hold_seconds = 300
    assert admission(coach_runtime, position)[0] is True


def test_frozen_season_limits_and_assessment_must_match(coach_runtime):
    engine = coach_runtime
    limits = engine.broker.risk_limits(engine.risk_mode).model_copy(
        update={"max_hold_seconds": 400, "hard_max_hold_seconds": 900}
    )
    engine.broker.season_profile = {
        "risk_mode": engine.risk_mode.value,
        "risk_limits": limits.model_dump(mode="json"),
    }
    assert admission(engine, held(engine, age=500))[0] is True
    assert admission(engine, held(engine, age=795))[0] is False


@pytest.mark.parametrize("arrival", [None, "pending", "stale_mark", "pressure", "hard_deadline"])
def test_complete_coach_review_resumes_and_rechecks_positions_after_screening(
    coach_runtime, monkeypatch, arrival
):
    from signal_arcade.coach import _build_candidates

    engine = coach_runtime
    position = held(engine)
    assert admission(engine, position) == (True, None)
    for index in range(30):
        engine.database.save_learning_observation(
            _observation(index, NOW - timedelta(hours=1) + timedelta(seconds=index))
        )
    coach = coach_for(engine.database, can_run=engine._coach_can_run)
    original = coach._optional_work
    position_before = position.model_dump(mode="json")
    injected = False

    async def work(function, *args, **kwargs):
        nonlocal injected
        result = await original(function, *args, **kwargs)
        if function is _build_candidates and not injected:
            injected = True
            if arrival == "pending":
                engine.broker.pending["urgent"] = object()
            elif arrival == "stale_mark":
                position.mark_is_stale = True
            elif arrival == "pressure":
                engine.last_processing_lag_seconds = 2
            elif arrival == "hard_deadline":
                position.opened_at = NOW - timedelta(seconds=1790)
        return result

    monkeypatch.setattr(coach, "_optional_work", work)
    asyncio.run(coach.tick())
    assert injected, "The real historical screening path did not run"
    if arrival is not None:
        assert coach.http.calls == 0
        assert engine.database.list_coach_reviews() == []
        assert engine.database.list_coach_hypotheses() == []
        engine.broker.pending.clear()
        engine.last_processing_lag_seconds = 0
        engine.broker.positions[position.mint] = Position.model_validate(position_before)
        asyncio.run(coach.tick())
    assert coach.http.calls == 1
    assert len(engine.database.list_coach_reviews()) == 1
    assert engine.database.list_coach_reviews()[0].valid
    assert len(engine.database.list_coach_hypotheses()) == 1
    assert engine.broker.positions[position.mint].model_dump(mode="json") == position_before
    assert engine.broker.pending == {}


@pytest.mark.parametrize("stage", ["quota", "request"])
def test_coach_enforces_inference_deadline_and_cleans_up_request(coach_runtime, monkeypatch, stage):
    from signal_arcade import coach as coach_module

    engine = coach_runtime
    assert admission(engine, held(engine))[0] is True
    for index in range(30):
        engine.database.save_learning_observation(
            _observation(index, NOW - timedelta(hours=1) + timedelta(seconds=index))
        )
    coach = coach_for(engine.database, can_run=engine._coach_can_run)
    coach.http = engine.http
    completed = False
    requested = False

    async def stall():
        nonlocal completed
        try:
            await asyncio.Event().wait()
        finally:
            completed = True

    async def stalled_request(request):
        nonlocal requested
        requested = True
        await stall()

    async def quota_available(*args, **kwargs):
        if stage == "quota":
            await stall()
        return True

    monkeypatch.setattr(coach_module, "COACH_INFERENCE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(coach.http.quota, "acquire", quota_available)

    async def run():
        await coach.http.client.aclose()
        coach.http.client = httpx.AsyncClient(transport=httpx.MockTransport(stalled_request))
        try:
            await asyncio.wait_for(coach.tick(), timeout=2)
            assert not coach.http.ollama_generation_busy
        finally:
            await coach.http.close()

    asyncio.run(run())
    assert requested is (stage == "request")
    assert completed
    assert coach.busy is False
    assert coach.last_error == "ollama_unavailable_or_timed_out"
    assert coach.next_attempt_at is not None
    assert len(engine.database.list_coach_reviews()) == 1
    assert not engine.database.list_coach_reviews()[0].valid
    assert engine.database.list_coach_hypotheses() == []


@pytest.mark.parametrize("stage", ["quota", "request"])
def test_external_cancellation_releases_inference_without_partial_proposal_and_can_retry(
    coach_runtime, monkeypatch, stage
):
    engine = coach_runtime
    position = held(engine)
    assert admission(engine, position)[0] is True
    position_before = position.model_dump(mode="json")
    for index in range(30):
        engine.database.save_learning_observation(
            _observation(index, NOW - timedelta(hours=1) + timedelta(seconds=index))
        )
    coach = coach_for(engine.database, can_run=engine._coach_can_run)
    coach.http = engine.http
    entered = asyncio.Event()
    completed = asyncio.Event()
    blocked = True
    requests = 0

    async def stall():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            completed.set()

    async def quota_available(*args, **kwargs):
        if blocked and stage == "quota":
            await stall()
        return True

    async def request_handler(request):
        nonlocal requests
        requests += 1
        if blocked and stage == "request":
            await stall()
        payload = json.loads(request.content)
        candidate_id = payload["format"]["properties"]["candidate_id"]["enum"][1]
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {"candidate_id": candidate_id, "summary": "Test the screened bounded rule."}
                )
            },
        )

    monkeypatch.setattr(coach.http.quota, "acquire", quota_available)

    async def run():
        nonlocal blocked
        await coach.http.client.aclose()
        coach.http.client = httpx.AsyncClient(transport=httpx.MockTransport(request_handler))
        task = asyncio.create_task(coach.tick())
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            assert coach.busy
            assert coach.http.ollama_generation_busy
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert completed.is_set()
            assert not coach.busy
            assert not coach.http.ollama_generation_busy
            assert coach.last_error is None
            assert coach.next_attempt_at is None
            assert engine.database.list_coach_reviews() == []
            assert engine.database.list_coach_hypotheses() == []
            blocked = False
            await asyncio.wait_for(coach.tick(), timeout=2)
            assert not coach.http.ollama_generation_busy
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await coach.http.close()

    asyncio.run(run())
    assert requests == (2 if stage == "request" else 1)
    assert not coach.busy
    reviews = engine.database.list_coach_reviews()
    assert len(reviews) == 1
    assert reviews[0].valid
    assert len(engine.database.list_coach_hypotheses()) == 1
    assert position.model_dump(mode="json") == position_before
    assert not engine.broker.pending
