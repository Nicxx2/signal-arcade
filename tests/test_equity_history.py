from datetime import UTC, datetime, timedelta

from signal_arcade.database import Database


def test_hourly_closes_cannot_overlap_recent_exact_checkpoints(settings):  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    start = datetime(2026, 9, 6, tzinfo=UTC)
    for minute, value in [(0, 100), (10, 200), (50, 120), (60, 140), (80, 160), (110, 180)]:
        database.record_equity(value, value - 10, recorded_at=start + timedelta(minutes=minute))
    result = database.compact_equity_history(recent_limit=2)
    assert len(result) == 3
    assert result[0]["kind"] == "hourly_close"
    assert result[0]["recorded_at"] == start.isoformat()
    assert result[0]["period_end"] == (start + timedelta(hours=1)).isoformat()
    assert result[0]["equity_lamports"] == 120
    assert result[0]["high_equity_lamports"] == 200
    assert result[0]["low_equity_lamports"] == 100
    assert [point["equity_lamports"] for point in result[1:]] == [160, 180]
    assert all(point["kind"] == "checkpoint" for point in result[1:])
    database.close()


def test_empty_equity_history_stays_empty(settings):  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    assert database.compact_equity_history() == []
    database.close()
