"""Ephemeral route proof follows holdings without altering saved terminal evidence."""

import asyncio
import copy
import json
from datetime import UTC, datetime

import pytest
from signal_arcade.models import Position
from signal_arcade.orchestrator import Orchestrator


@pytest.fixture
def engine(settings):
    value = Orchestrator(settings)
    yield value
    asyncio.run(value.http.close())
    value.database.close()


def position(mint="held", identity="current"):
    return Position(
        position_id=identity,
        mint=mint,
        symbol="TEST",
        token_units=1,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=datetime.now(UTC),
        entry_fill_id="entry-" + identity,
    )


@pytest.mark.parametrize("boundary", ["heartbeat", "watchdog"])
def test_existing_boundaries_drop_closed_probes_and_preserve_active_proof(engine, boundary):
    now = datetime.now(UTC)
    held = position()
    engine.broker.positions[held.mint] = held
    engine._record_position_route_probe(
        held.mint,
        available=False,
        observed_at=now,
        slot=10,
        market_status="dormant",
        blockers=["verified_empty_route"],
        position_id=held.position_id,
        route_proof={"route_identity": ["held"], "accounts": [1, 2]},
    )
    active = copy.deepcopy(engine._position_route_probes[held.mint])
    saved_terminal_evidence = {"probe": engine._position_route_probes[held.mint]}
    for index in range(250):
        engine._position_route_probes[f"closed-{index}"] = copy.deepcopy(active)
    before_bytes = len(json.dumps(engine._position_route_probes))
    if boundary == "heartbeat":
        engine._heartbeat_tick(now)
    else:
        engine._apply_position_watchdog_result([], {"slot": 11, "accounts": {}}, now)
    assert engine._position_route_probes == {held.mint: active}
    assert len(json.dumps(engine._position_route_probes)) < before_bytes / 100
    assert saved_terminal_evidence == {"probe": active}
    assert engine.broker.positions[held.mint] is held
    # A normal committed closure removes the holding. No later watchdog target is needed.
    engine.broker.positions.clear()
    engine._heartbeat_tick(now)
    assert not engine._position_route_probes
    assert saved_terminal_evidence == {"probe": active}


def test_same_mint_reentry_cannot_inherit_old_position_proof(engine):
    engine.broker.positions["held"] = position(identity="new")
    engine._position_route_probes["held"] = {"position_id": "old", "consecutive": 2}
    engine._heartbeat_tick(datetime.now(UTC))
    assert "held" not in engine._position_route_probes


def test_old_inflight_target_cannot_replace_new_position_probe(engine):
    held = position(identity="new")
    engine.broker.positions[held.mint] = held
    proof = {"position_id": "new", "consecutive": 2, "route_proof": {"kept": True}}
    engine._position_route_probes[held.mint] = copy.deepcopy(proof)
    engine._apply_position_watchdog_result(
        [{"mint": held.mint, "position_id": "old"}],
        {"slot": 11, "accounts": {}},
        datetime.now(UTC),
    )
    assert engine._position_route_probes[held.mint] == proof


def test_unidentified_legacy_probe_is_left_to_existing_validator(engine):
    engine.broker.positions["held"] = position()
    legacy = {"position_id": None, "consecutive": 1}
    engine._position_route_probes["held"] = legacy
    engine._prune_position_route_probes()
    assert engine._position_route_probes["held"] is legacy


def test_still_held_position_keeps_proof_when_no_sale_was_committed(engine):
    held = position()
    engine.broker.positions[held.mint] = held
    proof = {"position_id": held.position_id, "consecutive": 2}
    engine._position_route_probes[held.mint] = proof
    # A pending or failed sell has not removed the authoritative holding.
    engine._heartbeat_tick(datetime.now(UTC))
    assert engine._position_route_probes[held.mint] is proof
