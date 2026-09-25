"""Keep row adaptation conservative without shrinking for fixed commit overhead."""

from types import SimpleNamespace

import pytest
from signal_arcade.orchestrator import Orchestrator


def adapt(state, *, execute, total, exhausted=0, budget=0.05, completed=1, removed=50):
    Orchestrator._adapt_storage_history_chunks(
        state,
        {
            "raw_trades_query_seconds": total,
            "raw_trades_execute_seconds": execute,
            "raw_trades_completed_queries": completed,
            "raw_trades_query_budget_exhausted": exhausted,
            "raw_trades_query_budget_seconds": budget,
        },
        {"raw_trades": removed},
    )


def test_fixed_commit_overhead_does_not_collapse_chunks_or_trigger_growth():
    state = SimpleNamespace(_storage_history_chunk_rows={"raw_trades": 50})
    for _ in range(12):
        adapt(state, execute=0.002, total=0.067)
        assert state._storage_history_chunk_rows["raw_trades"] == 50
    state._storage_history_chunk_rows["raw_trades"] = 1
    adapt(state, execute=0.002, total=0.067, removed=1)
    assert state._storage_history_chunk_rows["raw_trades"] == 1
    for expected in (6, 11, 16):
        adapt(
            state,
            execute=0.002,
            total=0.008,
            removed=state._storage_history_chunk_rows["raw_trades"],
        )
        assert state._storage_history_chunk_rows["raw_trades"] == expected


@pytest.mark.parametrize("exhausted,completed", [(0, 1), (1, 0)])
def test_slow_execution_still_shrinks_under_original_wall_budget(exhausted, completed):
    state = SimpleNamespace(_storage_history_chunk_rows={"raw_trades": 50})
    adapt(state, execute=0.06, total=0.067, exhausted=exhausted, completed=completed)
    assert state._storage_history_chunk_rows["raw_trades"] == 25


@pytest.mark.parametrize("execute", [None, True, float("nan"), float("inf"), -1, 0.2, "unknown"])
def test_invalid_or_inconsistent_execution_measurement_never_tunes(execute):
    state = SimpleNamespace(_storage_history_chunk_rows={"raw_trades": 20})
    adapt(state, execute=execute, total=0.067)
    assert state._storage_history_chunk_rows["raw_trades"] == 20


def test_depleted_admission_budget_is_not_evidence_of_an_oversized_chunk():
    state = SimpleNamespace(_storage_history_chunk_rows={"raw_trades": 20})
    adapt(state, execute=0.04, total=0.044, exhausted=1, budget=0.003, completed=0)
    assert state._storage_history_chunk_rows["raw_trades"] == 20
