import asyncio
import threading
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import AdvisoryReadDeferred
from signal_arcade.models import Position, QuoteCurrency, RiskMode
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.risk_profiles import DrawdownPolicy, DrawdownPolicyKind
from test_long_season_accounting import save_trade


@pytest.fixture
def engine(settings):
    value = Orchestrator(settings)
    asyncio.run(value.setup_portfolio(QuoteCurrency.SOL, 1_000_000_000))
    yield value
    asyncio.run(value.http.close())
    value.database.close()


def open_trade(engine):
    at = datetime.now(UTC) - timedelta(minutes=10)
    buy, sell = save_trade(engine.database, "one", at)
    with engine.database._conn:
        engine.database._conn.execute("DELETE FROM fills WHERE side='sell'")
    position = Position(
        position_id="one",
        mint="one",
        symbol="ONE",
        token_units=100,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=at,
        entry_fill_id=buy.fill_id,
        last_mark_lamports=110,
        unrealized_pnl_lamports=10,
        last_marked_at=datetime.now(UTC),
        mark_is_stale=False,
        mark_is_executable=True,
    )
    engine.broker.positions[position.mint] = position
    engine.database.save_position(position)
    return sell


def close_trade(engine, sell):
    engine.database.save_fill(sell)
    engine.database.delete_position("one")
    engine.broker.positions.pop("one")


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("sort", ["recent", "profit", "loss"])
def test_fill_before_snapshot_retries_without_duplicate_or_missing_fees(
    engine, monkeypatch, side, sort
):
    sell = open_trade(engine) if side == "sell" else None
    original = engine.leaderboard
    calls = 0

    def interleaved(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            close_trade(engine, sell) if sell is not None else open_trade(engine)
        return original(**kwargs)

    monkeypatch.setattr(engine, "leaderboard", interleaved)
    result = asyncio.run(engine.leaderboard_view(sort=sort))
    assert calls == 2
    assert result["summary"]["open_trades"] == int(side == "buy")
    assert result["summary"]["closed_trades"] == int(side == "sell")
    assert result["summary"]["total_fees_minor"] == (5 if side == "buy" else 10)
    assert len(result["rows"]) <= 1
    assert not any(key.startswith("_") for key in result)


def test_sell_after_sql_snapshot_preserves_one_consistent_open_result(engine, monkeypatch):
    sell = open_trade(engine)
    original = engine.database.iter_fill_contexts

    def interleaved(**kwargs):
        history = original(**kwargs)
        try:
            first = next(history)
            close_trade(engine, sell)
            yield first
            yield from history
        finally:
            history.close()

    monkeypatch.setattr(engine.database, "iter_fill_contexts", interleaved)
    result = asyncio.run(engine.leaderboard_view(sort="recent"))
    assert [row["status"] for row in result["rows"]] == ["open"]
    assert result["summary"]["open_trades"] == 1
    assert result["summary"]["closed_trades"] == 0
    assert result["summary"]["total_fees_minor"] == 5


@pytest.mark.parametrize("view", ["leaderboard", "seasons"])
@pytest.mark.parametrize("rollover", [False, True])
def test_inflight_view_cannot_publish_across_season_or_currency_change(
    engine, monkeypatch, view, rollover
):
    entered, release = threading.Event(), threading.Event()
    original = engine.leaderboard if view == "leaderboard" else engine.database.list_paper_seasons
    calls = 0

    def delayed(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 1:
            entered.set()
            assert release.wait(3)
        return result

    target = engine if view == "leaderboard" else engine.database
    monkeypatch.setattr(
        target, "leaderboard" if view == "leaderboard" else "list_paper_seasons", delayed
    )

    async def exercise():
        if rollover:
            await engine.resume_trading()
        old_season = engine.broker.season_id
        read = asyncio.create_task(
            engine.leaderboard_view() if view == "leaderboard" else engine.seasons_view()
        )
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            await engine.request_season_profile(
                RiskMode.AGGRESSIVE,
                DrawdownPolicy(kind=DrawdownPolicyKind.DISABLED),
                target_quote_currency=QuoteCurrency.USDC,
                target_starting_minor=250_000_000,
            )
            if rollover:
                await engine._profile_transition_tick(datetime.now(UTC))
                assert engine.broker.season_id != old_season
            else:
                assert engine.broker.season_id == old_season
        finally:
            release.set()
        result = await read
        if view == "leaderboard":
            assert result["summary"]["quote_currency"] == "USDC"
            assert result["summary"]["quote_decimals"] == 6
        else:
            current = next(row for row in result["seasons"] if row["status"] == "current")
            assert current["quote_currency"] == "USDC"
            assert current["starting_minor"] == 250_000_000
        assert calls == 2

    asyncio.run(exercise())


@pytest.mark.parametrize("worker_error", [AdvisoryReadDeferred, RuntimeError])
def test_repeated_cancellation_keeps_reader_lock_until_worker_exits(
    engine, monkeypatch, worker_error
):
    entered, stopping, release, exited = (threading.Event() for _ in range(4))

    def delayed_stop(**kwargs):
        entered.set()
        while not kwargs["stop_requested"]():
            threading.Event().wait(0.001)
        stopping.set()
        try:
            assert release.wait(3)
        finally:
            exited.set()
        raise worker_error("reader stopped")

    monkeypatch.setattr(engine, "leaderboard", delayed_stop)

    async def exercise():
        task = asyncio.create_task(engine.leaderboard_view())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            assert await asyncio.to_thread(stopping.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            assert engine._ui_leaderboard_refresh_lock.locked()
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert exited.is_set()
        assert not engine._ui_leaderboard_refresh_lock.locked()
        assert not engine._ui_leaderboard_cache

    asyncio.run(exercise())


def test_changing_history_defers_after_bounded_retries_without_caching(engine, monkeypatch):
    original = engine.leaderboard
    calls = 0

    def changing(**kwargs):
        nonlocal calls
        calls += 1
        save_trade(engine.database, f"race-{calls}", datetime.now(UTC))
        return original(**kwargs)

    monkeypatch.setattr(engine, "leaderboard", changing)
    with pytest.raises(AdvisoryReadDeferred, match="accounting boundary"):
        asyncio.run(engine.leaderboard_view())
    assert calls == 2
    assert not engine._ui_leaderboard_cache
    assert not engine._ui_leaderboard_refresh_lock.locked()


def test_cancelled_results_stops_worker_before_another_scan(engine, monkeypatch):
    entered, exited = threading.Event(), threading.Event()

    def wait_for_cancel(**kwargs):
        entered.set()
        assert kwargs["stop_requested"] is not None
        while not kwargs["stop_requested"]():
            threading.Event().wait(0.001)
        exited.set()
        raise AdvisoryReadDeferred("cancelled")

    monkeypatch.setattr(engine, "leaderboard", wait_for_cancel)

    async def exercise():
        task = asyncio.create_task(engine.leaderboard_view())
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert exited.is_set()
        assert not engine._ui_leaderboard_refresh_lock.locked()
        assert not engine._ui_leaderboard_cache

    asyncio.run(exercise())


def test_cancelled_fill_reader_closes_sql_snapshot(engine):
    open_trade(engine)
    stopped = threading.Event()
    history = engine.database.iter_fill_contexts(page_size=1, stop_requested=stopped.is_set)
    next(history)
    stopped.set()
    with pytest.raises(AdvisoryReadDeferred):
        next(history)
    assert engine.database._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


@pytest.mark.parametrize("sort", ["recent", "profit", "loss"])
@pytest.mark.parametrize("executable", [False, True])
def test_closed_history_reuse_keeps_fresh_open_marks_fees_and_exact_totals(
    engine, monkeypatch, sort, executable
):
    sell = open_trade(engine)
    for i in range(25):
        save_trade(engine.database, f"closed-{i}", datetime.now(UTC), profit=i - 10)
    original = engine.database.iter_fill_contexts
    reads = []

    def counted(**kwargs):
        rows = 0
        for row in original(**kwargs):
            rows += 1
            yield row
        reads.append((kwargs.get("open_mints"), rows))

    monkeypatch.setattr(engine.database, "iter_fill_contexts", counted)

    def refresh():
        if sort in engine._ui_leaderboard_cache:
            engine._ui_leaderboard_cache[sort] = (0, engine._ui_leaderboard_cache[sort][1])
        return asyncio.run(engine.leaderboard_view(sort=sort))

    def comparable(board):
        return {
            **{key: value for key, value in board.items() if not key.startswith("_")},
            "rows": [
                {k: v for k, v in row.items() if k != "hold_seconds"} for row in board["rows"]
            ],
        }

    first = refresh()
    engine.broker.positions["one"].unrealized_pnl_lamports = 45
    engine.broker.positions["one"].mark_is_executable = executable
    updated = refresh()
    assert reads == [(None, 51), (["one"], 1)]
    reference = engine.leaderboard(
        sort=sort, limit=500, positions=list(engine.broker.positions.values())
    )
    assert comparable(updated) == comparable(reference)
    assert updated["summary"] == first["summary"]
    if sort == "recent":
        opened = next(row for row in updated["rows"] if row["status"] == "open")
        assert opened["pnl_minor"] == (45 if executable else -100)
        assert opened["last_known_pnl_minor"] == 45
    close_trade(engine, sell)
    reads.clear()
    closed = refresh()
    assert reads == [(None, 52)]
    assert closed["summary"]["open_trades"] == 0
    assert closed["summary"]["closed_trades"] == 26
    assert closed["summary"]["total_fees_minor"] == 260


@pytest.mark.parametrize("change", ["sort", "limit", "revision"])
def test_closed_cache_cannot_cross_sort_limit_or_history_boundaries(engine, change):
    for i in range(6):
        save_trade(engine.database, f"closed-{i}", datetime.now(UTC), profit=i - 3)
    revision = engine.database.paper_history_revision()
    first = engine.leaderboard(sort="profit", limit=1, history_revision=revision)
    sort, limit = "profit", 1
    if change == "sort":
        sort = "loss"
    elif change == "limit":
        limit = 4
    else:
        save_trade(engine.database, "new", datetime.now(UTC), profit=100)
        revision = engine.database.paper_history_revision()
    actual = engine.leaderboard(
        sort=sort, limit=limit, history_revision=revision, closed_history=first["_closed_history"]
    )
    expected = engine.leaderboard(sort=sort, limit=limit, history_revision=revision)
    assert actual == expected


@pytest.mark.parametrize("sort", ["recent", "profit", "loss"])
@pytest.mark.parametrize("limit", [0, 1, 6])
def test_repeated_closed_cache_preserves_invalid_and_legacy_receipt_accounting(engine, sort, limit):
    open_trade(engine)
    at = datetime.now(UTC) - timedelta(hours=1)
    for mint, profit in (("winner", 10), ("loser", -4), ("even", 0)):
        save_trade(engine.database, mint, at, profit=profit)
    _, invalid_sell = save_trade(engine.database, "invalid", at, profit=999)
    invalid_sell.filled_at = at - timedelta(seconds=1)
    # Construct a malformed historical receipt; the public writer is append-only.
    with engine.database._conn:
        engine.database._conn.execute(
            "UPDATE fills SET filled_at=?,record_json=? WHERE fill_id=?",
            (
                invalid_sell.filled_at.isoformat(),
                invalid_sell.model_dump_json(),
                invalid_sell.fill_id,
            ),
        )
    revision = engine.database.paper_history_revision()
    closed_history = None

    for executable in (True, False, True):
        position = engine.broker.positions["one"]
        position.mark_is_executable = executable
        position.unrealized_pnl_lamports = 45 if executable else 12
        board = engine.leaderboard(
            sort=sort,
            limit=limit,
            positions=[position],
            history_revision=revision,
            closed_history=closed_history,
        )
        closed_history = board["_closed_history"]
        summary = board["summary"]
        assert summary["closed_trades"] == 3
        assert summary["open_trades"] == 1
        assert summary["wins"] == summary["losses"] == 1
        assert summary["invalid_results"] == 1
        assert summary["legacy_unverified_results"] == 3
        assert summary["total_fees_minor"] == 35
        assert summary["total_realized_pnl_minor"] == 6
        assert board["available_rows"] == (5 if sort == "recent" else 3)
        assert len(board["rows"]) == min(limit, board["available_rows"])
        if sort != "recent":
            assert all(row["audit_status"] != "invalid" for row in board["rows"])
        elif limit == 6:
            invalid = next(row for row in board["rows"] if row["mint"] == "invalid")
            assert invalid["audit_status"] == "invalid"
            assert invalid["hold_seconds"] is None
            opened = next(row for row in board["rows"] if row["status"] == "open")
            assert opened["pnl_minor"] == (45 if executable else -100)
            assert opened["last_known_pnl_minor"] == (45 if executable else 12)
