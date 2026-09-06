from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from signal_arcade.config import Settings
from signal_arcade.intelligence.features import TokenState
from signal_arcade.intelligence.learning import (
    FEATURE_SCHEMA_VERSION,
    LearningEngine,
    _challenger_cohort_key,
)
from signal_arcade.models import (
    ChallengerSkill,
    DecisionAction,
    Position,
    RiskMode,
    StatisticalModelFamily,
)
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.providers.solana import PUMP_PROGRAM
from signal_arcade.strategy import BASELINE_VERSION
from signal_arcade.terminal_evidence import TERMINAL_PROBE_POLICY, valid_terminal_probe


@pytest.mark.parametrize("failure", ["missing", "owner", "decode", "rejected", "same_slot"])
def test_rejected_route_responses_cannot_write_off_inventory(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    engine = Orchestrator(settings)
    now = datetime.now(UTC)
    mint = "audit-mint"
    engine.features.tokens[mint] = TokenState(
        mint=mint,
        curve_address="audit-curve",
        last_event_at=now - timedelta(minutes=5),
    )
    engine.broker.positions[mint] = Position(
        position_id="audit-position",
        mint=mint,
        symbol="AUDIT",
        token_units=1,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=now - timedelta(hours=1),
        entry_fill_id="audit-fill",
        last_marked_at=now - timedelta(minutes=5),
        mark_is_stale=True,
    )
    account = (
        None
        if failure in {"missing", "same_slot"}
        else {
            "owner": "wrong" if failure == "owner" else PUMP_PROGRAM,
            "raw": b"fixture",
        }
    )
    monkeypatch.setattr(
        engine.solana, "decode_pump_bonding_curve", lambda _: {} if failure == "rejected" else None
    )
    monkeypatch.setattr(engine.features, "refresh_pump_curve", lambda *a, **kw: False)
    for index in range(2):
        _, refreshed, _ = engine._apply_position_watchdog_result(
            [{"mint": mint, "venue": "pump_curve", "curve_address": "audit-curve"}],
            {
                "slot": 100 if failure == "same_slot" else 100 + index,
                "accounts": {"audit-curve": account},
            },
            now + timedelta(seconds=index * 8),
        )
        assert not refreshed
    disposition, waiting = engine._terminal_position_dispositions(
        engine.broker.snapshot(RiskMode.BALANCED, persist_peak=False),
        now + timedelta(seconds=8),
    )
    assert disposition[mint]["terminal_disposition"] == "unknown"
    assert waiting == [mint]
    assert engine._position_route_probes[mint]["verified"] is False
    asyncio.run(engine.http.close())
    engine.database.close()


def test_terminal_proof_needs_distinct_slots_and_rejects_future_time(settings: Settings) -> None:
    engine = Orchestrator(settings)
    now = datetime.now(UTC)
    for index, slot in enumerate((100, 100, 101)):
        at = now + timedelta(seconds=index)
        engine._record_position_route_probe(
            "mint",
            available=False,
            observed_at=at,
            slot=slot,
            market_status="dormant",
            blockers=["fees exceed sell proceeds"],
        )
        evidence = {
            "policy": TERMINAL_PROBE_POLICY,
            "global_market_healthy": True,
            "probe": engine._position_route_probes["mint"],
        }
        assert valid_terminal_probe(evidence, at) is (index == 2)
    assert not valid_terminal_probe(evidence, now)
    assert not valid_terminal_probe(evidence, now + timedelta(seconds=181))
    asyncio.run(engine.http.close())
    engine.database.close()


@pytest.mark.parametrize("primary_present", [True, False])
def test_exit_tournament_scores_every_required_pair(primary_present: bool) -> None:
    mode, config = RiskMode.BALANCED, "audit-exit-cohort"
    key = _challenger_cohort_key(mode, config, BASELINE_VERSION, FEATURE_SCHEMA_VERSION)
    state = NS(
        skill=ChallengerSkill.EXIT,
        risk_mode=mode,
        configuration_fingerprint=config,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        testing_version="candidate",
        champion_version="champion",
        common_forward_count=0,
        last_tournament={},
        rejected_versions=[],
    )
    artifacts = {
        version: NS(
            version=version,
            model_family=StatisticalModelFamily.DETERMINISTIC,
            schema_version="challenger-skill-v2",
        )
        for version in ("candidate", "champion")
    }
    episodes = []
    for i in range(30):
        checkpoints = {"60": NS(net_return=0.2 if i == 0 else -0.3), "600": NS(net_return=0.0)}
        if primary_present:
            checkpoints["300"] = NS(net_return=0.1 if i == 0 else None)
        episodes.append(
            NS(
                mint=f"independent-{i}",
                risk_mode=mode,
                configuration_fingerprint=config,
                baseline_version=BASELINE_VERSION,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                baseline_action=DecisionAction.ENTER,
                baseline_actionable=True,
                checkpoints=checkpoints,
                challenger_evaluations={
                    "candidate": NS(skill=ChallengerSkill.EXIT, proposed_action="60"),
                    "champion": NS(skill=ChallengerSkill.EXIT, proposed_action="600"),
                },
            )
        )
    engine = NS(
        current_risk_mode=mode,
        configuration_fingerprint=lambda: config,
        baseline_version=lambda: BASELINE_VERSION,
        skill_states={(key, ChallengerSkill.EXIT): state},
        skill_artifacts=artifacts,
        _policy_evidence=lambda **kw: episodes,
        _append_champion_event=lambda *a, **kw: None,
        _start_next_skill_tournament=lambda *a: None,
        _promote_active_skill=lambda *a, **kw: None,
        database=NS(save_challenger_skill_state=lambda *a: None),
    )
    LearningEngine._advance_entry_tournaments(engine)
    assert state.champion_version == "champion"
    assert state.last_tournament["common_usable_count"] == 30
    assert state.last_tournament["candidate_harm_count"] == 29
    assert state.last_tournament["mean_uplift"] == pytest.approx(-0.283333333333)


def test_secondary_outcome_advances_governance_without_requesting_a_fit() -> None:
    calls = []
    engine = NS(
        _govern_active_model=lambda: calls.append("health"),
        _advance_entry_tournaments=lambda: calls.append("tournaments"),
        request_retraining=lambda **kw: calls.append("fit"),
        _govern_skill_ensemble=lambda: calls.append("ensemble"),
    )
    LearningEngine._advance_primary_outcomes(engine, set(), outcomes_changed=True)
    assert calls == ["health", "tournaments", "ensemble"]
