from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from signal_arcade.api import create_app
from signal_arcade.battle_replay import (
    MAX_REPLAY_BYTES,
    MAX_REPLAY_POINTS,
    freeze_replay,
    record_replay,
    start_replay,
    valid_replay,
)
from signal_arcade.database import Database
from signal_arcade.models import ChallengerChampionEvent, ChallengerSkillState
from test_v1104_training_history import history_state


def state_fixture():
    state = history_state()
    state.testing_version = "candidate"
    return state


def checkpoint(state, observed=40, usable=30, mean=0.02):
    state.last_tournament = {
        "candidate_version": state.testing_version,
        "champion_version": state.champion_version,
        "common_observed_count": observed,
        "common_usable_count": usable,
        "mean_uplift": mean,
        "uplift_lower_bound": mean - 0.03 if mean is not None else None,
        "uplift_upper_bound": mean + 0.03 if mean is not None else None,
    }
    record_replay(state, 30, 0.7)


def completed(state):
    last = state._battle_replay["points"][-1]
    event = ChallengerChampionEvent(
        event_id="recorded-event",
        occurred_at=datetime.now(UTC),
        skill=state.skill,
        kind="defended",
        candidate_version="candidate",
        previous_champion_version="crown",
        champion_version="crown",
        common_observed_count=last["observed"],
        common_usable_count=last["usable"],
        availability_fraction=last["coverage"],
        mean_uplift=last["mean"],
        uplift_lower_bound=last["lower"],
    )
    state.champion_journey.append(event)
    freeze_replay(state, event.event_id)
    return event


def test_records_exact_values_without_changing_authority_or_legacy_json():
    state = state_fixture()
    start_replay(state, 30, 0.7)
    checkpoint(state, 0, 0, None)
    checkpoint(state)
    original = state.model_dump_json()
    checkpoint(state)
    assert len(state._battle_replay["points"]) == 2
    assert state.model_dump_json() == original
    assert ChallengerSkillState.model_validate_json(original)._battle_replay is None
    assert valid_replay(state._battle_replay)
    assert not state._battle_replay["partial"]
    assert state._battle_replay["points"][-1]["coverage"] == 0.75


def test_mid_battle_capture_is_partial_and_keeps_real_turning_points_bounded():
    state = state_fixture()
    for index in range(500):
        mean = 0.04 if index == 200 else -0.03 if index == 350 else 0.0
        checkpoint(state, 40 + index, 30 + index, mean)
    replay = state._battle_replay
    assert replay["partial"] and replay["sampled"]
    assert len(replay["points"]) == MAX_REPLAY_POINTS
    assert replay["points"][0]["sequence"] == 0
    assert replay["points"][-1]["sequence"] == 499
    assert {0.04, -0.03}.issubset({point["mean"] for point in replay["points"]})
    assert len(json.dumps(replay).encode()) < MAX_REPLAY_BYTES
    assert valid_replay(replay)


def test_freezing_and_restart_preserve_result_and_isolate_next_pair(settings):
    database = Database(settings.database_path)
    state = state_fixture()
    start_replay(state, 30, 0.7)
    checkpoint(state)
    database.save_challenger_skill_state(state)
    loaded = database.list_challenger_skill_states()[0]
    assert loaded._battle_replay["partial"]
    checkpoint(loaded, 50, 40, -0.02)
    event = completed(loaded)
    frozen = copy.deepcopy(loaded._pending_battle_replays[event.event_id])
    loaded.testing_version = "next-candidate"
    start_replay(loaded, 30, 0.7)
    checkpoint(loaded, 0, 0, None)
    database.save_challenger_skill_state(loaded)
    assert database.champion_battle_replay(state.cohort_key, event.event_id) == frozen
    assert database.champion_battle_replay("different-cohort", event.event_id) is None
    assert database.champion_battle_replay(state.cohort_key, "older-event") is None
    assert loaded._pending_battle_replays == {}
    assert "battle_replay" not in loaded.model_dump_json()
    assert database._conn.execute("PRAGMA user_version").fetchone()[0] == 16
    database.close()


@pytest.mark.parametrize(
    "damage",
    [
        "pair",
        "cohort",
        "final",
        "bounds",
        "nonfinite",
        "count",
        "time",
        "order",
        "flags",
        "threshold",
        "size",
        "json",
        "oversized_number",
        "skill_type",
    ],
)
def test_invalid_or_mismatched_recordings_fail_closed(settings, damage):
    database = Database(settings.database_path)
    state = state_fixture()
    checkpoint(state)
    checkpoint(state, 50, 40, -0.02)
    event = completed(state)
    database.save_challenger_skill_state(state)
    replay = copy.deepcopy(state._battle_replay)
    if damage == "pair":
        replay["candidate_version"] = "wrong"
    if damage == "cohort":
        replay["cohort_key"] = "wrong"
    if damage == "final":
        replay["points"][-1]["mean"] = -0.01
    if damage == "bounds":
        replay["points"][0]["lower"] = 1
    if damage == "nonfinite":
        replay["points"][0]["mean"] = float("nan")
    if damage == "count":
        replay["points"][0]["usable"] = 41
    if damage == "time":
        replay["points"][0]["at"] = "invalid"
    if damage == "order":
        replay["points"][1]["sequence"] = 0
    if damage == "flags":
        replay["partial"] = "false"
    if damage == "threshold":
        replay["minimum_coverage"] = 0
    if damage == "oversized_number":
        replay["points"][0]["mean"] = 10**400
    if damage == "skill_type":
        replay["skill"] = []
    if damage == "size":
        replay["extra"] = "x" * MAX_REPLAY_BYTES
    raw = "invalid" if damage == "json" else json.dumps(replay)
    with database._conn:
        database._conn.execute(
            "UPDATE champion_battle_replays SET record_json=? WHERE replay_key=?",
            (raw, f"event:{event.event_id}"),
        )
    assert database.champion_battle_replay(state.cohort_key, event.event_id) is None
    if damage in {"oversized_number", "skill_type"}:
        with database._conn:
            database._conn.execute("UPDATE champion_battle_replays SET record_json=?", (raw,))
        assert database.list_challenger_skill_states()[0]._battle_replay is None
    database.close()


def test_recording_ignores_invalid_samples_and_clock_regression():
    state = state_fixture()
    checkpoint(state)
    before = copy.deepcopy(state._battle_replay)
    checkpoint(state, 1, 2)
    checkpoint(state, mean=float("inf"))
    assert state._battle_replay == before
    state._battle_replay["points"][-1]["at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    checkpoint(state, 50, 40)
    assert len(state._battle_replay["points"]) == 1
    assert state._battle_replay["partial"]


def test_event_and_replay_are_atomic_in_publication(settings):
    database = Database(settings.database_path)
    state = state_fixture()
    checkpoint(state)
    event = completed(state)
    with pytest.raises(RuntimeError, match="rollback"), database.training_publication():
        database.save_challenger_skill_state(state.model_copy(deep=True))
        raise RuntimeError("rollback")
    assert database._conn.execute("SELECT COUNT(*) FROM champion_battle_replays").fetchone()[0] == 0
    assert (
        database._conn.execute("SELECT COUNT(*) FROM challenger_champion_events").fetchone()[0] == 0
    )
    database.save_challenger_skill_state(state)
    assert database.champion_battle_replay(state.cohort_key, event.event_id)
    database.close()


def test_optional_endpoint_is_bounded_and_cohort_scoped(settings):
    with TestClient(create_app(settings)) as client:
        snapshot = client.get("/api/v1/snapshot").json()
        cohort = snapshot["learning"]["champion_journey_cohort_key"]
        path = "/api/v1/learning/champion-replay"
        response = client.get(path, params={"event_id": "missing", "cohort_key": cohort})
        assert response.status_code == 200
        assert response.json() == {"event_id": "missing", "cohort_key": cohort, "timeline": None}
        assert (
            client.get(path, params={"event_id": "missing", "cohort_key": "old"}).status_code == 409
        )
        assert (
            client.get(path, params={"event_id": "x" * 181, "cohort_key": cohort}).status_code
            == 422
        )
        assert client.get(path).status_code == 422
