import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from test_battle_replay import checkpoint, completed, state_fixture


def test_identical_skill_state_does_not_repeat_writes(settings):
    database = Database(settings.database_path)
    state = state_fixture()
    checkpoint(state)
    database.save_challenger_skill_state(state)
    saved_at = state.updated_at
    statements = []
    database._conn.set_trace_callback(statements.append)
    try:
        for index in range(20):
            state.updated_at = saved_at + timedelta(seconds=index + 1)
            database.save_challenger_skill_state(state)
        assert not any(
            sql.startswith(("INSERT", "UPDATE", "BEGIN", "COMMIT")) for sql in statements
        )
        assert state.updated_at == saved_at
    finally:
        database._conn.set_trace_callback(None)
        database.close()


def test_replay_and_pending_history_are_saved_even_with_same_readout(settings):
    database = Database(settings.database_path)
    state = state_fixture()
    checkpoint(state)
    try:
        database.save_challenger_skill_state(state)
        state._battle_replay["partial"] = True
        state._battle_replay_dirty = True
        database.save_challenger_skill_state(state)
        row = database._conn.execute(
            "SELECT record_json FROM champion_battle_replays WHERE replay_key=?",
            (f"active:{state.cohort_key}:{state.skill.value}",),
        ).fetchone()
        assert json.loads(row[0])["partial"]
        event = completed(state)
        database.save_challenger_skill_state(state)
        assert database.champion_battle_replay(state.cohort_key, event.event_id)
        state.pending_versions.append("next")
        database.save_challenger_skill_state(state)
        restored = database.list_challenger_skill_states()[0]
        assert restored.pending_versions == ["next"]
        assert restored.champion_journey[-1] == event
    finally:
        database.close()


@pytest.mark.parametrize("failure", ["statement", "publication"])
def test_failed_skill_save_is_retried_without_another_evidence_change(settings, failure):
    database = Database(settings.database_path)
    state = state_fixture()
    database.save_challenger_skill_state(state)
    state.common_forward_count = 17
    state.updated_at = datetime.now(UTC)
    try:
        if failure == "statement":
            database._conn.execute(
                "CREATE TEMP TRIGGER reject_skill BEFORE UPDATE ON "
                "challenger_skill_states BEGIN SELECT RAISE(ABORT,'injected'); END"
            )
            with pytest.raises(sqlite3.IntegrityError):
                database.save_challenger_skill_state(state)
            database._conn.execute("DROP TRIGGER reject_skill")
        else:
            with pytest.raises(RuntimeError, match="rollback"), database.training_publication():
                database.save_challenger_skill_state(state)
                raise RuntimeError("rollback")
        database.save_challenger_skill_state(state)
        row = database._reader_conn.execute(
            "SELECT record_json FROM challenger_skill_states"
        ).fetchone()
        assert json.loads(row[0])["common_forward_count"] == 17
    finally:
        database.close()


def test_restart_and_cache_eviction_preserve_skill_state(settings):
    database = Database(settings.database_path)
    state = state_fixture()
    try:
        for index in range(270):
            other = state.model_copy(deep=True, update={"cohort_key": f"cohort-{index}"})
            database.save_challenger_skill_state(other)
        database.save_challenger_skill_state(state)
    finally:
        database.close()

    database = Database(settings.database_path)
    try:
        state.common_forward_count = 19
        database.save_challenger_skill_state(state)
        assert (
            next(
                item
                for item in database.list_challenger_skill_states()
                if item.cohort_key == state.cohort_key
            ).common_forward_count
            == 19
        )
    finally:
        database.close()


def test_publication_rollback_keeps_unsaved_replay_for_retry(settings):
    database = Database(settings.database_path)
    state = state_fixture()
    checkpoint(state)
    event = completed(state)
    try:
        with pytest.raises(RuntimeError, match="rollback"), database.training_publication():
            database.save_challenger_skill_state(state)
            raise RuntimeError("rollback")
        database.save_challenger_skill_state(state)
        assert database.champion_battle_replay(state.cohort_key, event.event_id) is not None
    finally:
        database.close()
