"""Optional assessment persistence must not block the loop or lose committed outcomes."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from signal_arcade.ai_lab import PROMPT_VERSION, SCHEMA_VERSION, AiDecisionLab
from signal_arcade.models import (
    AiCriticAssessment,
    AiDecisionMode,
    DecisionAction,
    EventKind,
    MarketEvent,
)
from test_ai_lab import FakeHttp, _decision
from test_probe_retention import engine  # noqa: F401
from test_v1104_refresh import route_fixture


def assessment(mint="fixture"):
    now = datetime.now(UTC)
    return AiCriticAssessment(
        assessment_id="fixture",
        decision_id="fixture",
        mint=mint,
        symbol="TEST",
        snapshot_at=now,
        mode=AiDecisionMode.SHADOW,
        model_name="fixture",
        model_digest="",
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        input_sha256="0" * 64,
        latency_ms=0,
        valid=False,
        invalid_reason="offline_fixture",
        baseline_action=DecisionAction.ENTER,
        outcome_due_at=now + timedelta(seconds=300),
    )


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_save_handoff_is_responsive_joined_and_tracks_only_committed_results(
    engine, monkeypatch, cancel, fail
):
    lab = engine.ai_lab
    value = assessment()
    entered, release = Event(), Event()
    saved = engine.database.save_ai_assessment

    def save(item):
        entered.set()
        assert release.wait(3)
        if fail:
            raise ValueError("fixture failed write")
        saved(item)

    monkeypatch.setattr(engine.database, "save_ai_assessment", save)

    async def run():
        task = asyncio.create_task(lab._save_assessment(value))
        assert await asyncio.to_thread(entered.wait, 2), "save blocked the event loop"
        assert lab.assessment_busy and not lab.has_pending_outcome(value.mint)
        tick = asyncio.create_task(lab.settle_assessment_for_mint(value.mint))
        await lab.settle_assessment_for_mint("unrelated")
        lab.mode = AiDecisionMode.OFF  # Completed evidence retains its original identity/mode.
        if cancel:
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
        assert not task.done() and not tick.done()
        release.set()
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                await task
        elif fail:
            with pytest.raises(ValueError, match="failed write"):
                await task
        else:
            await task
        await tick  # Optional failure does not fail the market task.
        assert not lab.assessment_busy
        assert lab.has_pending_outcome(value.mint) == (not fail)
        assert engine._event_priority_revision == int(not fail)
        rows = engine.database.list_ai_assessments()
        assert len(rows) == int(not fail)
        if rows:
            assert rows[0].model_dump() == value.model_dump()
        restored = AiDecisionLab(
            engine.database,
            FakeHttp(),
            engine.settings,
            select_model=lambda _: None,
            configuration_fingerprint=lambda: "test",
        )
        assert restored.has_pending_outcome(value.mint) == (not fail)

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_first_due_tick_cannot_overtake_same_mint_registration(engine, monkeypatch):
    state, _, _, now = route_fixture()
    value = assessment(state.mint).model_copy(update={"outcome_due_at": now})
    entered, release = Event(), Event()
    saved = engine.database.save_ai_assessment

    def save(item):
        entered.set()
        assert release.wait(3)
        saved(item)

    seen = []

    def observe(token, at):
        assert token is state and engine.ai_lab.has_pending_outcome(state.mint)
        seen.append(at)
        return 0

    monkeypatch.setattr(engine.database, "save_ai_assessment", save)
    monkeypatch.setattr(engine.features, "apply", lambda _: state)
    monkeypatch.setattr(engine, "_event_regresses_verified_route", lambda _: False)
    monkeypatch.setattr(engine, "_accept_event_order", lambda *_: True)
    monkeypatch.setattr(engine.ai_lab, "observe_market", observe)
    engine.running = False

    async def run():
        save_task = asyncio.create_task(engine.ai_lab._save_assessment(value))
        assert await asyncio.to_thread(entered.wait, 2)
        tick = asyncio.create_task(
            engine._handle_persisted_event(
                MarketEvent(
                    event_id="due",
                    source="test",
                    kind=EventKind.TRADE,
                    mint=state.mint,
                    received_at=now,
                )
            )
        )
        await asyncio.sleep(0)
        assert not tick.done() and not seen
        release.set()
        await asyncio.gather(tick, save_task)
        assert seen == [now]

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_shadow_stop_joins_commit_registration_and_balances_queue(engine, monkeypatch):
    lab = engine.ai_lab
    lab.mode = AiDecisionMode.SHADOW
    value = assessment()
    entered, release = Event(), Event()
    saved = engine.database.save_ai_assessment

    async def assess(*_, **__):
        return value

    def save(item):
        entered.set()
        assert release.wait(3)
        saved(item)

    monkeypatch.setattr(lab, "_assess", assess)
    monkeypatch.setattr(engine.database, "save_ai_assessment", save)

    async def run():
        decision = _decision(datetime.now(UTC)).model_copy(update={"mint": value.mint})
        lab.queue.put_nowait((decision, {}))
        lab.queued_mints.add(value.mint)
        lab.worker = asyncio.create_task(lab._worker_loop())
        assert await asyncio.to_thread(entered.wait, 2)
        await lab.pause_for_maintenance()
        assert lab.assessment_busy  # Inference has ended, but the save has not.
        stop = asyncio.create_task(lab.stop())
        await asyncio.sleep(0)
        assert not stop.done()
        lab.worker.cancel()
        release.set()
        await stop
        await asyncio.wait_for(lab.queue.join(), 1)
        assert lab.has_pending_outcome(value.mint)
        assert not lab.queued_mints and not lab.assessment_busy

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_upgrade_waits_for_saved_assessment_handoff_even_after_inference(engine, monkeypatch):
    calls = []
    original = engine._update_maintenance_operation
    busy = [True]

    async def update(*args, **kwargs):
        calls.append(kwargs.get("stage"))
        return await original(*args, **kwargs)

    monkeypatch.setattr(engine, "_update_maintenance_operation", update)
    monkeypatch.setattr(type(engine.ai_lab), "assessment_busy", property(lambda _: busy[0]))

    async def run():
        await engine.begin_upgrade_preparation()
        task = engine._maintenance_operation_task
        assert task is not None
        for _ in range(100):
            if "pausing_optional_ai" in calls:
                break
            await asyncio.sleep(0.01)
        assert "pausing_optional_ai" in calls and "finishing_storage_work" not in calls
        busy[0] = False
        await asyncio.wait_for(task, 3)
        assert "finishing_storage_work" in calls
        assert engine.maintenance_operation_status()["state"] == "ready"
        await engine.cancel_upgrade_preparation()
        assert not engine.ai_lab.maintenance_paused

    asyncio.run(run())


def test_upgrade_times_out_without_declaring_an_unsettled_assessment_ready(engine, monkeypatch):
    monkeypatch.setattr(type(engine.ai_lab), "assessment_busy", property(lambda _: True))
    monkeypatch.setattr("signal_arcade.orchestrator._UPGRADE_AI_SETTLE_SECONDS", 0.001)

    async def run():
        await engine.begin_upgrade_preparation()
        assert engine._maintenance_operation_task is not None
        await asyncio.wait_for(engine._maintenance_operation_task, 3)
        assert engine.maintenance_operation_status()["state"] == "failed"
        assert not engine.ai_lab.maintenance_paused

    asyncio.run(run())
