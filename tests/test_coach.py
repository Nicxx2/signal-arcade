from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from signal_arcade.coach import (
    AiCoach,
    _build_candidates,
    _evaluate_hypothesis,
)
from signal_arcade.database import SCHEMA_VERSION, Database
from signal_arcade.models import (
    ChallengerSizeTrial,
    ChallengerSkill,
    CoachExperimentKind,
    CoachExperimentState,
    CoachHypothesis,
    CoachReview,
    DecisionAction,
    LearningCheckpoint,
    LearningObservation,
    LearningObservationStatus,
    RiskMode,
)


class FakeCoachHttp:
    ollama_generation_busy = False

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls = 0

    async def ollama_structured(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        timeout_seconds: float,
        model: str | None = None,
    ) -> tuple[str, int] | None:
        del prompt, timeout_seconds, model
        self.calls += 1
        if not self.available:
            return None
        choices = schema["properties"]["candidate_id"]["enum"]
        return json.dumps({"candidate_id": choices[1], "summary": "Test the cautious rule."}), 17


class InventingCoachHttp(FakeCoachHttp):
    async def ollama_structured(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        timeout_seconds: float,
        model: str | None = None,
    ) -> tuple[str, int] | None:
        del prompt, schema, timeout_seconds, model
        self.calls += 1
        return json.dumps(
            {
                "candidate_id": "invented-rule",
                "summary": "Buy more.",
                "action": "enter",
            }
        ), 12


def _observation(
    index: int,
    created_at: datetime,
    *,
    outcome: float | None = -0.20,
    momentum: float = -0.10,
    season: str = "season-1",
    fingerprint: str = "fp",
    include_checkpoint: bool = True,
    baseline_version: str = "baseline-v1.1",
    feature_schema_version: str = "challenger-features-v1",
    active_skill_versions: dict[str, str] | None = None,
) -> LearningObservation:
    checkpoints = {}
    if include_checkpoint:
        checkpoints["300"] = LearningCheckpoint(
            horizon_seconds=300,
            observed_at=created_at + timedelta(seconds=300),
            net_return=outcome,
            missing_reason=None if outcome is not None else "no_fresh_trade_near_horizon",
        )
    return LearningObservation(
        observation_id=f"observation-{index}",
        decision_id=f"decision-{index}",
        mint=f"Mint{index:044d}",
        symbol="TEST",
        created_at=created_at,
        baseline_action=DecisionAction.ENTER,
        risk_mode=RiskMode.BALANCED,
        baseline_edge_index=0.04,
        baseline_composite=80,
        features={
            "opportunity": 0.8,
            "danger": 0.1,
            "execution": 0.95,
            "confidence": 0.9,
            "buy_ratio": 0.7,
            "wallet_breadth": 0.7,
            "concentration": 0.1,
            "repetition": 0.1,
            "coordination": 0.1,
            "curve_progress": 0.5,
            "momentum": momentum,
            "drawdown": 0.05,
            "reserve_depth": 0.7,
            "single_trade_wallet_ratio": 0.5,
            "round_trip_wallet_ratio": 0.05,
            "round_trip_volume_ratio": 0.1,
            "net_quote_flow_ratio": 0.7,
            "side_alternation_ratio": 0.4,
            "quantized_amount_repeat_ratio": 0.15,
            "slot_concentration_hhi": 0.1,
            "price_direction_consistency": 0.6,
        },
        token_units=1_000,
        entry_cost_lamports=25_000_000,
        entry_price_impact_fraction=0.01,
        fee_bps=125,
        checkpoints=checkpoints,
        status=(
            LearningObservationStatus.COMPLETE
            if include_checkpoint
            else LearningObservationStatus.PENDING
        ),
        baseline_actionable=True,
        season_id=season,
        configuration_fingerprint=fingerprint,
        baseline_version=baseline_version,
        feature_schema_version=feature_schema_version,
        active_skill_versions=active_skill_versions or {},
    )


def _hypothesis(cutoff: datetime) -> CoachHypothesis:
    return CoachHypothesis(
        hypothesis_id="hypothesis-1",
        signature="signature-1",
        coach_review_id="review-1",
        created_at=cutoff,
        updated_at=cutoff,
        cutoff_at=cutoff,
        kind=CoachExperimentKind.ENTRY_VETO,
        title="Test weak momentum",
        rationale="Forward test only.",
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="fp",
        model_name="qwen3.5:2b",
        feature_name="momentum",
        operator="<=",
        threshold=0,
        discovery_observed_count=30,
        discovery_usable_count=30,
        discovery_availability_fraction=1,
        discovery_mean_uplift=0.2,
        discovery_uplift_lower_bound=0.1,
    )


def _hold_observation(
    index: int,
    created_at: datetime,
    *,
    action: DecisionAction,
    actionable: bool,
    selected_return: float,
    baseline_return: float,
) -> LearningObservation:
    observation = _observation(index, created_at, momentum=0.10)
    checkpoints = {
        "60": LearningCheckpoint(
            horizon_seconds=60,
            observed_at=created_at + timedelta(seconds=60),
            net_return=selected_return,
        ),
        "300": LearningCheckpoint(
            horizon_seconds=300,
            observed_at=created_at + timedelta(seconds=300),
            net_return=selected_return,
        ),
        "600": LearningCheckpoint(
            horizon_seconds=600,
            observed_at=created_at + timedelta(seconds=600),
            net_return=baseline_return,
        ),
    }
    return observation.model_copy(
        update={
            "baseline_action": action,
            "baseline_actionable": actionable,
            "checkpoints": checkpoints,
        }
    )


def test_candidate_screening_is_bounded_and_never_applied() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [_observation(index, now + timedelta(seconds=index)) for index in range(30)]
    candidates = _build_candidates(rows, RiskMode.BALANCED, "fp", set())
    assert candidates
    assert all(item.kind in CoachExperimentKind for item in candidates)
    assert all(item.feature_name in {"momentum"} for item in candidates)

    hypothesis = _hypothesis(now)
    assert hypothesis.influence_applied is False
    assert "action" not in hypothesis.model_dump()
    assert "position_size" not in hypothesis.model_dump()


def test_market_integrity_rule_is_only_a_forward_test_candidate() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(30):
        observation = _observation(
            index,
            now + timedelta(seconds=index),
            momentum=0.10,
        )
        rows.append(
            observation.model_copy(
                update={
                    "features": {
                        **observation.features,
                        "single_trade_wallet_ratio": 0.96,
                    }
                }
            )
        )

    candidates = _build_candidates(rows, RiskMode.BALANCED, "fp", set())
    integrity = [item for item in candidates if item.feature_name == "single_trade_wallet_ratio"]
    assert len(integrity) == 1
    assert integrity[0].kind == CoachExperimentKind.MANIPULATION_VETO
    assert integrity[0].uplift_lower_bound > 0


def test_single_suspicious_launch_cannot_create_integrity_experiment() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(19):
        observation = _observation(
            index,
            now + timedelta(seconds=index),
            momentum=0.10,
        )
        rows.append(
            observation.model_copy(
                update={
                    "features": {
                        **observation.features,
                        "single_trade_wallet_ratio": 0.99,
                    }
                }
            )
        )

    candidates = _build_candidates(rows, RiskMode.BALANCED, "fp", set())
    assert all(item.feature_name != "single_trade_wallet_ratio" for item in candidates)


def test_discovery_with_poor_exit_coverage_cannot_consume_a_forward_slot() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _observation(
            index,
            now + timedelta(seconds=index),
            outcome=-0.20 if index < 25 else None,
        )
        for index in range(40)
    ]
    assert _build_candidates(rows, RiskMode.BALANCED, "fp", set()) == []


def test_earlier_review_experiments_ignore_counterfactual_pass_rows() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    pass_rows = [
        _hold_observation(
            index,
            now + timedelta(seconds=index),
            action=DecisionAction.PASS,
            actionable=False,
            selected_return=0.40,
            baseline_return=-0.40,
        )
        for index in range(30)
    ]
    assert _build_candidates(pass_rows, RiskMode.BALANCED, "fp", set()) == []

    hypothesis = _hypothesis(now).model_copy(
        update={
            "kind": CoachExperimentKind.EARLIER_REVIEW,
            "feature_name": None,
            "operator": None,
            "threshold": None,
            "hold_seconds": 300,
        }
    )
    entry_rows = [
        _hold_observation(
            100 + index,
            now + timedelta(seconds=100 + index),
            action=DecisionAction.ENTER,
            actionable=True,
            selected_return=0.10,
            baseline_return=0.0,
        )
        for index in range(10)
    ]
    updated = _evaluate_hypothesis(
        hypothesis,
        [*pass_rows, *entry_rows],
        now + timedelta(hours=1),
    )
    assert updated.forward_observed_count == 10
    assert updated.forward_usable_count == 10


def test_forward_evaluation_never_reuses_discovery_rows() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    old = [_observation(index, cutoff - timedelta(minutes=1), outcome=-0.9) for index in range(50)]
    new = [
        _observation(
            100 + index,
            cutoff + timedelta(seconds=index + 1),
            outcome=-0.2,
            season="season-1" if index < 30 else "season-2",
        )
        for index in range(60)
    ]
    updated = _evaluate_hypothesis(_hypothesis(cutoff), [*old, *new], cutoff + timedelta(hours=1))
    assert updated.forward_observed_count == 60
    assert updated.forward_usable_count == 60
    assert updated.forward_season_count == 2
    assert updated.forward_mean_uplift == 0.2
    assert updated.state == CoachExperimentState.PROMISING
    assert updated.influence_applied is False


def test_missing_forward_exits_cannot_qualify() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _observation(
            index,
            cutoff + timedelta(seconds=index + 1),
            outcome=(-0.2 if index < 90 else None),
            season="season-1" if index < 90 else "season-2",
        )
        for index in range(180)
    ]
    updated = _evaluate_hypothesis(_hypothesis(cutoff), rows, cutoff + timedelta(hours=1))
    assert updated.forward_observed_count == 180
    assert updated.forward_usable_count == 90
    assert updated.forward_availability_fraction == 0.5
    assert updated.state == CoachExperimentState.INCONCLUSIVE
    assert updated.resolution_reason == "maximum_forward_evidence_reached"


def test_low_volume_forward_study_expires_without_waiting_forever() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _observation(
            index,
            cutoff + timedelta(days=1, seconds=index),
            outcome=-0.2,
        )
        for index in range(10)
    ]

    updated = _evaluate_hypothesis(
        _hypothesis(cutoff),
        rows,
        cutoff + timedelta(days=91),
    )

    assert updated.forward_observed_count == 10
    assert updated.forward_usable_count == 10
    assert updated.state == CoachExperimentState.INCONCLUSIVE
    assert updated.resolution_reason == "forward_study_expired"


def test_inconclusive_result_is_retained_but_releases_the_context_slot(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-inconclusive.sqlite3")
    hypothesis = _hypothesis(datetime.now(UTC)).model_copy(
        update={"state": CoachExperimentState.INCONCLUSIVE}
    )
    database.save_coach_hypothesis(hypothesis)
    coach = AiCoach(  # type: ignore[arg-type]
        database,
        FakeCoachHttp(),
        enabled=lambda: True,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 100,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (True, None),
    )

    status = coach.status()

    assert status["state"] == "inconclusive"
    assert status["recent_hypotheses"][0]["state"] == "inconclusive"
    assert status["recent_hypotheses"][0]["context_active"] is True
    gates = {gate["id"]: gate for gate in status["qualification_gates"]}
    assert gates["experiment_selected"]["state"] == "passed"
    assert gates["forward_outcomes"]["state"] == "not_met"
    assert status["qualification_passed"] < status["qualification_total"]
    later_rows = [
        _observation(index, hypothesis.cutoff_at + timedelta(seconds=index + 1))
        for index in range(120)
    ]
    assert (
        _evaluate_hypothesis(
            hypothesis,
            later_rows,
            hypothesis.cutoff_at + timedelta(hours=2),
        )
        == hypothesis
    )
    database.close()


def test_forward_support_needs_multiple_seasons_and_repeated_reads_do_not_mutate() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _observation(index, cutoff + timedelta(seconds=index + 1), season="season-1")
        for index in range(60)
    ]
    hypothesis = _hypothesis(cutoff)
    evaluated_at = cutoff + timedelta(hours=1)
    updated = _evaluate_hypothesis(hypothesis, rows, evaluated_at)
    assert updated.forward_usable_count == 60
    assert updated.forward_season_count == 1
    assert updated.state == CoachExperimentState.TESTING
    assert updated.last_evaluated_at == evaluated_at

    repeated = _evaluate_hypothesis(updated, rows, evaluated_at + timedelta(minutes=1))
    assert repeated == updated
    assert repeated.updated_at == updated.updated_at


def test_forward_evidence_accumulates_durably_inside_exact_provenance() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    hypothesis = _hypothesis(cutoff).model_copy(
        update={"dependency_versions": {"entry": "champion-entry"}}
    )
    first = [
        _observation(
            index,
            cutoff + timedelta(seconds=index + 1),
            season="season-1",
            active_skill_versions={"entry": "champion-entry"},
        )
        for index in range(30)
    ]
    first_result = _evaluate_hypothesis(hypothesis, first, cutoff + timedelta(hours=1))
    assert first_result.forward_usable_count == 30

    second = [
        _observation(
            100 + index,
            cutoff + timedelta(hours=2, seconds=index),
            season="season-2",
            active_skill_versions={"entry": "champion-entry"},
        )
        for index in range(30)
    ]
    wrong_dependency = _observation(
        999,
        cutoff + timedelta(hours=2, minutes=1),
        season="season-2",
        active_skill_versions={"entry": "different-entry"},
    )
    completed = _evaluate_hypothesis(
        first_result,
        [*second, wrong_dependency],
        cutoff + timedelta(hours=3),
    )

    assert completed.forward_observed_count == 60
    assert completed.forward_usable_count == 60
    assert completed.forward_season_count == 2
    assert completed.state == CoachExperimentState.PROMISING
    assert wrong_dependency.observation_id not in completed.forward_observation_ids


def test_forward_season_gate_requires_meaningful_samples_in_each_season() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _observation(
            index,
            cutoff + timedelta(seconds=index + 1),
            season="season-1" if index < 55 else "season-2",
        )
        for index in range(60)
    ]

    updated = _evaluate_hypothesis(_hypothesis(cutoff), rows, cutoff + timedelta(hours=1))

    assert updated.forward_usable_count == 60
    assert updated.forward_season_count == 1
    assert updated.state == CoachExperimentState.TESTING


def test_manipulation_lane_can_screen_fixed_multi_signal_patterns() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(30):
        observation = _observation(index, now + timedelta(seconds=index), momentum=0.1)
        rows.append(
            observation.model_copy(
                update={
                    "features": {
                        **observation.features,
                        "round_trip_volume_ratio": 0.8,
                        "net_quote_flow_ratio": 0.1,
                    }
                }
            )
        )

    candidates = _build_candidates(rows, RiskMode.BALANCED, "fp", set())
    paired = [
        item
        for item in candidates
        if item.skill == ChallengerSkill.MANIPULATION and len(item.conditions) == 2
    ]

    assert paired
    assert {condition.feature_name for condition in paired[0].conditions} == {
        "round_trip_volume_ratio",
        "net_quote_flow_ratio",
    }


def test_sizing_lane_uses_fee_inclusive_counterfactual_trials() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(30):
        observation = _observation(index, now + timedelta(seconds=index), momentum=0.1)
        rows.append(
            observation.model_copy(
                update={
                    "size_trials": {
                        "1": ChallengerSizeTrial(
                            multiplier=1,
                            budget_lamports=100,
                            token_units=100,
                            entry_cost_lamports=100,
                            entry_price_impact_fraction=0.01,
                            eligible_at_entry=True,
                            checkpoints={
                                "300": LearningCheckpoint(
                                    horizon_seconds=300,
                                    observed_at=now + timedelta(seconds=300),
                                    exit_value_lamports=105,
                                    net_return=0.05,
                                )
                            },
                        ),
                        "1.5": ChallengerSizeTrial(
                            multiplier=1.5,
                            budget_lamports=150,
                            token_units=150,
                            entry_cost_lamports=150,
                            entry_price_impact_fraction=0.015,
                            eligible_at_entry=True,
                            checkpoints={
                                "300": LearningCheckpoint(
                                    horizon_seconds=300,
                                    observed_at=now + timedelta(seconds=300),
                                    exit_value_lamports=175,
                                    net_return=25 / 150,
                                )
                            },
                        ),
                    }
                }
            )
        )

    candidates = _build_candidates(rows, RiskMode.BALANCED, "fp", set())
    sizing = [item for item in candidates if item.skill == ChallengerSkill.SIZING]

    assert len(sizing) == 1
    assert sizing[0].size_multiplier == 1.5
    assert sizing[0].uplift_lower_bound > 0


def test_negative_forward_evidence_rejects_an_experiment() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _observation(
            index,
            cutoff + timedelta(seconds=index + 1),
            outcome=0.20,
            season="season-1" if index < 60 else "season-2",
        )
        for index in range(120)
    ]
    updated = _evaluate_hypothesis(_hypothesis(cutoff), rows, cutoff + timedelta(hours=1))
    assert updated.forward_mean_uplift == -0.20
    assert updated.forward_uplift_upper_bound == -0.20
    assert updated.state == CoachExperimentState.NOT_SUPPORTED


def test_tick_creates_durable_zero_influence_forward_experiment(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach.sqlite3")
    now = datetime.now(UTC) - timedelta(hours=1)
    for index in range(30):
        database.save_learning_observation(_observation(index, now + timedelta(seconds=index)))
    http = FakeCoachHttp()
    coach = AiCoach(  # type: ignore[arg-type]
        database,
        http,
        enabled=lambda: True,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 80,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (True, None),
    )
    asyncio.run(coach.tick())
    assert http.calls == 1
    assert len(coach.hypotheses) == 1
    assert coach.hypotheses[0].influence_applied is False
    assert coach.hypotheses[0].forward_observed_count == 0

    restarted = AiCoach(  # type: ignore[arg-type]
        database,
        http,
        enabled=lambda: True,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 80,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (True, None),
    )
    assert restarted.hypotheses[0].hypothesis_id == coach.hypotheses[0].hypothesis_id
    assert database.list_coach_reviews(10)[0].valid is True
    database.close()


def test_overload_and_ollama_failure_never_block_or_create_hypothesis(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-failure.sqlite3")
    now = datetime.now(UTC) - timedelta(hours=1)
    for index in range(30):
        database.save_learning_observation(_observation(index, now + timedelta(seconds=index)))
    http = FakeCoachHttp(available=False)
    overloaded = True
    coach = AiCoach(  # type: ignore[arg-type]
        database,
        http,
        enabled=lambda: True,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 80,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (not overloaded, "protecting_market_throughput"),
    )
    asyncio.run(coach.tick())
    assert http.calls == 0
    assert coach.paused_reason == "protecting_market_throughput"

    overloaded = False
    asyncio.run(coach.tick())
    assert http.calls == 1
    assert coach.hypotheses == []
    assert coach.last_error == "ollama_unavailable_or_timed_out"
    assert database.list_coach_reviews(10)[0].valid is False
    database.close()


def test_invented_or_action_bearing_model_output_is_rejected(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-invalid-output.sqlite3")
    now = datetime.now(UTC) - timedelta(hours=1)
    for index in range(30):
        database.save_learning_observation(_observation(index, now + timedelta(seconds=index)))
    http = InventingCoachHttp()
    coach = AiCoach(  # type: ignore[arg-type]
        database,
        http,
        enabled=lambda: True,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 80,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (True, None),
    )

    asyncio.run(coach.tick())

    assert coach.hypotheses == []
    assert coach.last_error == "invalid_structured_response"
    saved = database.list_coach_reviews(10)[0]
    assert saved.valid is False
    assert saved.selected_candidate_id is None
    database.close()


def test_context_change_during_inference_discards_the_result(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-context-change.sqlite3")
    now = datetime.now(UTC) - timedelta(hours=1)
    for index in range(30):
        database.save_learning_observation(_observation(index, now + timedelta(seconds=index)))
    calls = 0

    def context() -> tuple[RiskMode, str]:
        nonlocal calls
        calls += 1
        return (RiskMode.BALANCED, "fp") if calls == 1 else (RiskMode.SAFE, "changed-fingerprint")

    coach = AiCoach(  # type: ignore[arg-type]
        database,
        FakeCoachHttp(),
        enabled=lambda: True,
        context=context,
        outcomes_seen=lambda: 80,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (True, None),
    )

    asyncio.run(coach.tick())

    assert coach.last_error == "context_changed_during_review"
    assert coach.hypotheses == []
    assert database.list_coach_reviews() == []
    database.close()


def test_pause_during_inference_discards_the_result(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-pause-during-inference.sqlite3")
    now = datetime.now(UTC) - timedelta(hours=1)
    for index in range(30):
        database.save_learning_observation(_observation(index, now + timedelta(seconds=index)))
    enabled = True

    class PausingCoachHttp(FakeCoachHttp):
        async def ollama_structured(
            self,
            *,
            prompt: str,
            schema: dict[str, Any],
            timeout_seconds: float,
            model: str | None = None,
        ) -> tuple[str, int] | None:
            nonlocal enabled
            enabled = False
            return await super().ollama_structured(
                prompt=prompt,
                schema=schema,
                timeout_seconds=timeout_seconds,
                model=model,
            )

    coach = AiCoach(  # type: ignore[arg-type]
        database,
        PausingCoachHttp(),
        enabled=lambda: enabled,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 80,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (True, None),
    )

    asyncio.run(coach.tick())

    assert coach.paused_reason == "research_paused_during_review"
    assert coach.hypotheses == []
    assert database.list_coach_reviews() == []
    database.close()


def test_ready_contribution_works_while_research_paused_and_prioritizes_new_ready_work(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "coach-paused-contribution.sqlite3")
    now = datetime.now(UTC)
    waiting = _hypothesis(now).model_copy(
        update={
            "hypothesis_id": "waiting-newer",
            "signature": "waiting-newer-signature",
            "state": CoachExperimentState.PROMISING,
            "contribution_state": "waiting_for_champion",
        }
    )
    ready = _hypothesis(now - timedelta(seconds=1)).model_copy(
        update={
            "hypothesis_id": "ready-older",
            "signature": "ready-older-signature",
            "state": CoachExperimentState.PROMISING,
            "contribution_state": "ready",
        }
    )
    database.save_coach_hypothesis(waiting)
    database.save_coach_hypothesis(ready)
    coach = AiCoach(  # type: ignore[arg-type]
        database,
        FakeCoachHttp(),
        enabled=lambda: False,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 100,
        model_provenance=lambda: ("qwen3.5:2b", "digest-1"),
        can_run=lambda: (True, None),
        contribution_enabled=lambda: True,
    )

    selected = coach.ready_contribution()

    assert selected is not None
    assert selected.hypothesis_id == "ready-older"
    database.close()


def test_database_round_trips_coach_artifacts(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-round-trip.sqlite3")
    now = datetime.now(UTC)
    review = CoachReview(
        review_id="review-1",
        created_at=now,
        cutoff_at=now,
        outcomes_seen=80,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="fp",
        model_name="qwen3.5:2b",
        prompt_version="v1",
        schema_version="v1",
        input_sha256="a" * 64,
        candidate_count=1,
        latency_ms=10,
        valid=True,
        selected_candidate_id="candidate-1",
        summary="Bounded test.",
    )
    hypothesis = _hypothesis(now)
    database.save_coach_review(review)
    database.save_coach_hypothesis(hypothesis)
    assert database.list_coach_reviews() == [review]
    assert database.list_coach_hypotheses() == [hypothesis]
    stats = database.storage_stats(force=True)
    assert stats["coach_reviews"] == 1
    assert stats["coach_hypotheses"] == 1
    database.close()


def test_coach_selection_is_atomic_and_duplicate_safe(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-atomic.sqlite3")
    now = datetime.now(UTC)
    review = CoachReview(
        review_id="review-atomic",
        created_at=now,
        cutoff_at=now,
        outcomes_seen=80,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="fp",
        model_name="qwen3.5:2b",
        prompt_version="v3",
        schema_version="v3",
        input_sha256="c" * 64,
        candidate_count=1,
        latency_ms=10,
        valid=True,
        selected_candidate_id="candidate-atomic",
        summary="Bounded selection.",
    )
    hypothesis = _hypothesis(now).model_copy(update={"coach_review_id": review.review_id})

    assert database.save_coach_selection(review, hypothesis) is True
    assert database.save_coach_selection(review, hypothesis) is False
    assert database.storage_stats(force=True)["coach_reviews"] == 1
    assert database.storage_stats(force=True)["coach_hypotheses"] == 1
    database.close()


def test_coach_pruning_preserves_active_studies_and_their_review(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-pruning.sqlite3")
    now = datetime.now(UTC)
    active_review = CoachReview(
        review_id="review-active",
        created_at=now,
        cutoff_at=now,
        outcomes_seen=80,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="fp",
        model_name="qwen3.5:2b",
        prompt_version="v3",
        schema_version="v3",
        input_sha256="d" * 64,
        candidate_count=1,
        latency_ms=10,
        valid=True,
        selected_candidate_id="candidate-active",
    )
    active = _hypothesis(now).model_copy(update={"coach_review_id": active_review.review_id})
    terminal_review = active_review.model_copy(
        update={
            "review_id": "review-terminal",
            "created_at": now + timedelta(seconds=1),
            "cutoff_at": now + timedelta(seconds=1),
            "input_sha256": "e" * 64,
        }
    )
    terminal = _hypothesis(now + timedelta(seconds=1)).model_copy(
        update={
            "hypothesis_id": "hypothesis-terminal",
            "signature": "signature-terminal",
            "coach_review_id": terminal_review.review_id,
            "state": CoachExperimentState.INCONCLUSIVE,
        }
    )
    assert database.save_coach_selection(active_review, active)
    assert database.save_coach_selection(terminal_review, terminal)

    database.prune_coach_history(max_reviews=1, max_hypotheses=1)

    assert {item.hypothesis_id for item in database.list_coach_hypotheses()} == {
        active.hypothesis_id,
        terminal.hypothesis_id,
    }
    assert {item.review_id for item in database.list_coach_reviews()} == {
        active_review.review_id,
        terminal_review.review_id,
    }
    database.close()


def test_corrupt_optional_coach_rows_do_not_stop_valid_history(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-corrupt.sqlite3")
    now = datetime.now(UTC)
    valid = _hypothesis(now)
    database.save_coach_hypothesis(valid)
    with database._lock, database._conn:  # noqa: SLF001
        database._conn.execute(  # noqa: SLF001
            "INSERT INTO coach_hypotheses VALUES(?,?,?,?,?,?,?)",
            (
                "corrupt",
                (now + timedelta(seconds=1)).isoformat(),
                "testing",
                "entry_veto",
                "balanced",
                "fp",
                "{not-json",
            ),
        )

    assert database.list_coach_hypotheses() == [valid]
    database.close()


def test_schema_six_upgrade_adds_coach_storage_without_touching_settings(tmp_path: Path) -> None:
    path = tmp_path / "coach-migration.sqlite3"
    database = Database(path)
    database.set_setting("preserved_user_setting", {"keep": True})
    database.close()

    connection = sqlite3.connect(path)
    connection.executescript(
        """
        DROP TABLE coach_reviews;
        DROP TABLE coach_hypotheses;
        PRAGMA user_version=6;
        """
    )
    connection.close()

    upgraded = Database(path)
    assert upgraded.get_setting("preserved_user_setting") == {"keep": True}
    tables = {
        row[0]
        for row in upgraded._conn.execute(  # noqa: SLF001
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"coach_reviews", "coach_hypotheses"}.issubset(tables)
    assert (
        upgraded._conn.execute("PRAGMA user_version").fetchone()[0]  # noqa: SLF001
        == SCHEMA_VERSION
    )
    upgraded.close()


def test_storage_cache_cannot_overwrite_a_concurrent_invalidation(tmp_path: Path) -> None:
    database = Database(tmp_path / "coach-storage-race.sqlite3")
    now = datetime.now(UTC)
    review = CoachReview(
        review_id="review-race",
        created_at=now,
        cutoff_at=now,
        outcomes_seen=80,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="fp",
        model_name="qwen3.5:2b",
        prompt_version="v1",
        schema_version="v1",
        input_sha256="b" * 64,
        candidate_count=1,
        latency_ms=10,
        valid=True,
        selected_candidate_id="none",
        summary="No bounded experiment selected.",
    )
    counted = threading.Event()
    release = threading.Event()
    original_page_usage = database._page_usage  # noqa: SLF001

    def delayed_page_usage() -> dict[str, int]:
        result = original_page_usage()
        counted.set()
        assert release.wait(timeout=2)
        return result

    database._page_usage = delayed_page_usage  # type: ignore[method-assign]  # noqa: SLF001
    first: dict[str, dict[str, int]] = {}
    reader = threading.Thread(
        target=lambda: first.setdefault("stats", database.storage_stats(force=True))
    )
    reader.start()
    assert counted.wait(timeout=2)
    database.save_coach_review(review)
    release.set()
    reader.join(timeout=2)
    assert not reader.is_alive()
    database._page_usage = original_page_usage  # type: ignore[method-assign]  # noqa: SLF001

    assert first["stats"]["coach_reviews"] == 0
    assert database.storage_stats()["coach_reviews"] == 1
    database.close()
