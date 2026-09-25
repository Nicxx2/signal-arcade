"""Equity attribution observes the same queries and atomic writes, never fresh authority."""

# ruff: noqa: F811 -- shared fixture

import asyncio
import sqlite3

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.orchestrator import _detailed_to_thread
from signal_arcade.work_timing import WORK_DETAIL
from test_broker_work_budget import held  # noqa: F401


def test_snapshot_measurement_adds_no_database_reads_or_portfolio_changes(held):
    broker, database, _state, _now = held
    broker.snapshot()
    observed = []
    database._reader_conn.set_trace_callback(observed.append)
    baseline = broker.snapshot(persist_peak=False)
    queries = list(observed)
    observed.clear()
    detail = {}
    token = WORK_DETAIL.set(detail)
    try:
        measured = broker.snapshot(persist_peak=False)
    finally:
        WORK_DETAIL.reset(token)
        database._reader_conn.set_trace_callback(None)
    assert observed == queries
    assert measured.cash_lamports == baseline.cash_lamports
    assert measured.equity_lamports == baseline.equity_lamports
    assert detail["broker_snapshot"][0] == 1
    assert detail["ledger_read_lock"][0] == 1
    assert detail["setting_read_lock"][0] > 0


@pytest.mark.parametrize("failure", [False, True])
def test_equity_timing_preserves_commit_and_rollback(held, failure):
    broker, database, _state, now = held
    before = database._conn.execute("SELECT COUNT(*) FROM equity_points").fetchone()[0]
    recorded = broker._last_equity_recorded_at
    if failure:
        database._conn.execute(
            "CREATE TEMP TRIGGER deny_equity BEFORE INSERT ON equity_rollups "
            "BEGIN SELECT RAISE(ABORT, 'equity denied'); END"
        )
    detail = {}
    token = WORK_DETAIL.set(detail)
    try:
        if failure:
            with pytest.raises(sqlite3.IntegrityError, match="equity denied"):
                broker._record_equity(now, force=True)
        else:
            broker._record_equity(now, force=True)
    finally:
        WORK_DETAIL.reset(token)
    assert database._conn.execute("SELECT COUNT(*) FROM equity_points").fetchone()[0] == (
        before if failure else before + 1
    )
    assert broker._last_equity_recorded_at == (recorded if failure else now)
    for field in (
        "broker_equity",
        "broker_snapshot",
        "equity_save",
        "equity_write_lock",
        "equity_commit",
    ):
        assert detail[field][0] == 1
    assert not database._conn.in_transaction


def test_joined_broker_sample_keeps_equity_and_order_parts_together(held, tmp_path):
    broker, _database, _state, now = held
    recorder = DiagnosticsRecorder(tmp_path)
    asyncio.run(_detailed_to_thread(recorder, "broker", broker._record_equity, now, force=True))
    sample = recorder.runtime_evidence.slow["broker"]
    assert sample["outcome"] == "complete"
    assert {"broker_equity", "equity_save", "equity_commit", "broker_dispatch"} <= sample[
        "phases"
    ].keys()
    assert "equity_save" in recorder.work_detail_since_boot["equity"]
    assert "equity_save" not in recorder.work_detail_since_boot["broker"]
