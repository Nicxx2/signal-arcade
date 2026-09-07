from __future__ import annotations

import asyncio
import copy
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from signal_arcade import diagnostics_store as storage
from signal_arcade.diagnostics import (
    PHASES,
    PROOF_METRICS,
    DiagnosticsRecorder,
    PipelineCursor,
    artifact_summary,
    identity,
)
from signal_arcade.diagnostics_store import (
    DiagnosticsStore,
    decode,
    merge_hour,
    read_events,
    read_page,
)
from signal_arcade.orchestrator import Orchestrator
from test_v1104_training_history import training_fixture


def interval(seq=0, *, boot="a" * 32, at=1_788_600_000):
    return {
        "boot": boot,
        "seq": seq,
        "start": at + seq * 60,
        "end": at + (seq + 1) * 60,
        "elapsed": 60,
        "flags": [],
        "context": {"build": "first", "risk": "balanced"},
        "pipeline": {
            "processed": 9,
            "enqueued": 10,
            "shed": 1,
            "expired": 0,
            "reordered": 0,
            "lag_count": 9,
            "critical_count": 1,
            "lag_max": 2,
            "critical_lag_max": 0.5,
            "queue_max": 20,
            "lag_histogram": [0, 0, 6, 0, 3, 0, 0, 0, 0],
            "critical_histogram": [0, 0, 1, 0, 0, 0, 0, 0, 0],
        },
        "phases": {"snapshot": [1, 0.01, 0.01]},
        "skills": [],
        "gauges": {},
        "events": [{"kind": "training", "models": 1}],
    }


def test_duplicate_restart_and_rollup_are_atomic(tmp_path):
    store = DiagnosticsStore(tmp_path)
    assert store.append(interval())
    assert store.append(interval())
    assert store.append(interval(1))
    rows = read_page(tmp_path, tier=1, before=2e9)
    assert len(rows) == 1
    assert rows[0]["record"]["pipeline"]["processed"] == 18
    assert rows[0]["record"]["pipeline"]["lag_histogram"] == [0, 0, 12, 0, 6, 0, 0, 0, 0]
    assert len(read_events(tmp_path, before=2e9)) == 2
    store.close()
    store = DiagnosticsStore(tmp_path)
    assert store.append(interval(0, boot="b" * 32))
    assert len(read_page(tmp_path, tier=0, before=2e9)) == 3
    assert "multiple_boots" in read_page(tmp_path, tier=1, before=2e9)[0]["record"]["flags"]
    store.close()


def test_rollup_failure_rolls_back_interval_and_event(tmp_path, monkeypatch):
    store = DiagnosticsStore(tmp_path)
    store.append(interval())
    monkeypatch.setattr(storage, "CLEAN_BYTES", 4096)
    monkeypatch.setattr(storage, "RESERVE_BYTES", 0)
    monkeypatch.setattr(
        storage, "merge_hour", lambda *_: (_ for _ in ()).throw(ValueError("fault"))
    )
    with pytest.raises(ValueError):
        store.append(interval(1))
    assert len(read_page(tmp_path, tier=0, before=2e9)) == 1
    assert len(read_events(tmp_path, before=2e9)) == 1
    assert store.counts[0] == 1 and store.early_evictions == 0
    store.close()


def test_retry_after_detail_expiry_does_not_double_count_hour(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "MINUTE_ROWS", 1)
    store = DiagnosticsStore(tmp_path)
    store.append(interval())
    store.append(interval(1))
    assert len(read_page(tmp_path, tier=0, before=2e9)) == 1
    store.close()
    store = DiagnosticsStore(tmp_path)
    store.append(interval())
    assert read_page(tmp_path, tier=1, before=2e9)[0]["record"]["pipeline"]["processed"] == 18
    store.close()


def test_event_queue_is_immutable_and_oversize_does_not_lose_interval(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    event = {"kind": "training", "phases": {"fit_seconds": 1}}
    recorder.event(event)
    event["phases"]["fit_seconds"] = 99
    recorder.event({"kind": "training", "oversize": "x" * 3000})
    assert recorder.dropped == 1
    assert recorder.events[0]["phases"]["fit_seconds"] == 1
    values = interval()
    recorder.collect(pipeline=values["pipeline"], context=values["context"], gauges={}, skills=[])
    assert len(recorder.queue) == 1


def test_oversize_event_preserves_interval_and_marks_omission(tmp_path):
    import random

    rng = random.Random(9)  # noqa: S311 - deterministic compression fixture
    record = interval()
    record["events"] = [{"kind": "future", "details": rng.randbytes(900).hex()}]
    store = DiagnosticsStore(tmp_path)
    assert store.append(record)
    saved = read_page(tmp_path, tier=0, before=2e9)[0]["record"]
    assert saved["omitted_events"] == 1
    assert "event_omitted" in saved["flags"]
    assert saved["pipeline"]["processed"] == 9
    assert read_events(tmp_path, before=2e9) == []
    record = interval(1)
    assert store.append(record)
    assert read_page(tmp_path, tier=1, before=2e9)[0]["record"]["omitted_events"] == 1
    store.close()


def test_hour_counts_extrema_context_and_gaps():
    first, second = interval(), interval(2)
    second["context"] = {"build": "second"}
    second["pipeline"]["lag_max"] = 50
    merged = merge_hour(first, second)
    assert merged["elapsed"] == 120
    assert merged["pipeline"]["lag_max"] == 50
    assert merged["phases"]["snapshot"] == [2, 0.02, 0.01]
    assert set(merged["flags"]) == {"recording_gap", "mixed_context"}


def test_retention_keeps_rollups_and_bounded_event_history(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "MINUTE_ROWS", 3)
    monkeypatch.setattr(storage, "HOUR_ROWS", 2)
    monkeypatch.setattr(storage, "EVENT_ROWS", 2)
    store = DiagnosticsStore(tmp_path)
    for seq in range(10):
        store.append(interval(seq))
    assert len(read_page(tmp_path, tier=0, before=2e9)) == 3
    assert len(read_events(tmp_path, before=2e9)) == 2
    assert read_page(tmp_path, tier=1, before=2e9)[0]["record"]["pipeline"]["processed"] == 90
    assert store.early_evictions == 7
    store.close()


@pytest.mark.parametrize("fault", ["corrupt", "future", "foreign"])
def test_bad_schema_preserves_bytes(tmp_path, fault):
    path = tmp_path / "history.sqlite3"
    if fault == "corrupt":
        path.write_bytes(b"bad file, preserve me")
    else:
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE preserve_me (value)")
            if fault == "future":
                connection.execute("PRAGMA user_version=999")
    previous = path.read_bytes()
    with pytest.raises((sqlite3.DatabaseError, ValueError)):
        DiagnosticsStore(tmp_path)
    assert path.read_bytes() == previous


def test_low_disk_and_budget_pause_then_resume(tmp_path, monkeypatch):
    store = DiagnosticsStore(tmp_path)
    disk = storage.shutil.disk_usage(tmp_path)
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: disk._replace(free=0))
    assert not store.append(interval())
    assert read_page(tmp_path, tier=0) == []
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: disk._replace(free=2**40))
    assert store.append(interval())
    monkeypatch.setattr(storage, "PAUSE_BYTES", 1)
    monkeypatch.setattr(storage, "RESUME_BYTES", 1)
    assert not store.append(interval(1))
    assert store.status()["state"] == "paused_storage"
    store.close()


def test_reusable_pages_do_not_cause_repeated_detail_eviction(tmp_path, monkeypatch):
    store = DiagnosticsStore(tmp_path)
    with store.connection:
        store.connection.execute("CREATE TABLE temporary_padding (value)")
        store.connection.execute("INSERT INTO temporary_padding VALUES (zeroblob(524288))")
        store.connection.execute("DROP TABLE temporary_padding")
    monkeypatch.setattr(storage, "CLEAN_BYTES", 256 * 1024)
    monkeypatch.setattr(storage, "RESERVE_BYTES", 64 * 1024)
    assert storage.owned_bytes(tmp_path) > storage.CLEAN_BYTES
    assert store.append(interval())
    assert store.append(interval(1))
    assert len(read_page(tmp_path, tier=0, before=2e9)) == 2
    assert store.early_evictions == 0
    store.close()


def test_live_page_pressure_reclaims_detail_before_insert(tmp_path, monkeypatch):
    import random

    monkeypatch.setattr(storage, "CLEAN_BYTES", 1024 * 1024)
    monkeypatch.setattr(storage, "RESERVE_BYTES", 256 * 1024)
    store = DiagnosticsStore(tmp_path)
    rng = random.Random(33)  # noqa: S311 - deterministic storage pressure fixture
    padding = rng.randbytes(1800).hex()
    for sequence in range(400):
        record = interval(sequence)
        record["gauges"] = {"padding": padding}
        assert store.append(record)
    assert store.early_evictions > 0
    assert store.counts[0] > 0
    assert (
        sum(
            row["record"]["pipeline"]["processed"]
            for row in read_page(tmp_path, tier=1, before=2e9)
        )
        == 3600
    )
    assert store.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


def test_readonly_leaves_committed_data(tmp_path):
    store = DiagnosticsStore(tmp_path)
    store.append(interval())
    store.connection.execute("PRAGMA query_only=ON")
    with pytest.raises(sqlite3.OperationalError):
        store.append(interval(1))
    assert len(read_page(tmp_path, tier=0, before=2e9)) == 1
    store.close()


def test_sqlite_full_rolls_back_without_losing_committed_history(tmp_path):
    store = DiagnosticsStore(tmp_path)
    store.append(interval())
    pages = store.connection.execute("PRAGMA page_count").fetchone()[0]
    store.connection.execute(f"PRAGMA max_page_count={pages}")
    caught = None
    for sequence in range(1, 100):
        try:
            store.append(interval(sequence))
        except sqlite3.OperationalError as error:
            caught = error
            break
    assert caught is not None and caught.sqlite_errorcode == sqlite3.SQLITE_FULL
    rows = read_page(tmp_path, tier=0, before=2e9)
    assert len(rows) == sequence
    assert sum(row["record"]["pipeline"]["processed"] for row in rows) == sequence * 9
    assert (
        sum(
            row["record"]["pipeline"]["processed"]
            for row in read_page(tmp_path, tier=1, before=2e9)
        )
        == sequence * 9
    )
    assert store.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


def test_long_reader_bounds_wal_and_resumes_after_reader_closes(tmp_path, monkeypatch):
    # Scaled thresholds exercise exactly the production pause/checkpoint/hysteresis path.
    monkeypatch.setattr(storage, "PAUSE_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(storage, "RESUME_BYTES", 1024 * 1024)
    store = DiagnosticsStore(tmp_path)
    store.append(interval())
    reader = sqlite3.connect(store.path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM intervals").fetchone()
    for sequence in range(1, 1000):
        if not store.append(interval(sequence)):
            break
    else:
        pytest.fail("A pinned WAL must eventually pause recording")
    assert store.status()["state"] == "paused_storage"
    assert storage.owned_bytes(tmp_path) < 3 * 1024 * 1024
    reader.close()
    assert store.append(interval(sequence))
    assert store.status()["state"] == "recording"
    assert store.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


def test_writer_rechecks_pressure_and_stops_while_deferred(tmp_path):
    async def scenario():
        permitted = False
        recorder = DiagnosticsRecorder(tmp_path, can_write=lambda: permitted)
        await recorder.start()
        try:
            values = interval()
            recorder.collect(
                pipeline=values["pipeline"], context=values["context"], gauges={}, skills=[]
            )
            await recorder.flush_one(allowed=True)
            await asyncio.sleep(0.15)
            assert read_page(tmp_path, tier=0) == []
            permitted = True
            for _ in range(100):
                if recorder.status().get("ranges", {}).get("minute", {}).get("rows") == 1:
                    break
                await asyncio.sleep(0.02)
            assert recorder.status()["ranges"]["minute"]["rows"] == 1
            permitted = False
            recorder.collect(
                pipeline=values["pipeline"], context=values["context"], gauges={}, skills=[]
            )
            await recorder.flush_one(allowed=True)
            await asyncio.sleep(0.05)
        finally:
            await recorder.stop()
        assert not recorder.writer.thread.is_alive()
        assert len(read_page(tmp_path, tier=0)) == 1

    asyncio.run(scenario())


def test_bad_metric_slots_cannot_alias_proof_names():
    import zlib

    for slots in ([[-1, 1]], [[True, 1]], [[999, 1]], [[0, 1], [0, 2]]):
        with pytest.raises(ValueError, match="invalid_record"):
            decode(zlib.compress(json.dumps({"metric_values": slots}).encode()))


def test_reporting_fault_does_not_change_a_published_fit(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    monkeypatch.setattr(
        engine.diagnostics, "event", lambda _: (_ for _ in ()).throw(ValueError("observer fault"))
    )
    engine._record_training_diagnostics(
        SimpleNamespace(phase_seconds={}, key=(engine.risk_mode, "fixture")), True, time.monotonic()
    )
    assert engine.diagnostics.dropped == 1
    engine.database.close()


@pytest.mark.parametrize(
    "key,value",
    [("seq", -1), ("seq", True), ("boot", "bad"), ("elapsed", float("nan")), ("events", [{}] * 17)],
)
def test_invalid_records_do_not_write(tmp_path, key, value):
    store = DiagnosticsStore(tmp_path)
    record = interval()
    record[key] = value
    with pytest.raises(ValueError):
        store.append(record)
    assert read_page(tmp_path, tier=0) == []
    store.close()


def test_payload_and_decompression_are_bounded(tmp_path):
    store = DiagnosticsStore(tmp_path)
    record = interval()
    record["gauges"] = {"oversize": "x" * 40_000}
    with pytest.raises(ValueError, match="too_large"):
        store.append(record)
    import zlib

    with pytest.raises(ValueError):
        decode(zlib.compress(b"x" * 100_000))
    store.close()


def test_pipeline_cursor_does_not_repeat_counts_or_old_peaks():
    cursor = PipelineCursor()
    bucket = {"serial": 1, **interval()["pipeline"]}
    first, gap = cursor.take([bucket])
    assert first["processed"] == 9 and not gap
    second, _ = cursor.take([bucket])
    assert second["processed"] == 0 and second["lag_max"] == 0
    next_bucket = {**bucket, "serial": 4}
    result, gap = cursor.take([next_bucket])
    assert gap and result["processed"] == 9


def test_bounded_handoff_pressure_and_clock_jump(tmp_path, monkeypatch):
    recorder = DiagnosticsRecorder(tmp_path)
    values = interval()
    for _ in range(50):
        recorder.collect(
            pipeline=values["pipeline"], context=values["context"], gauges={}, skills=[]
        )
    assert len(recorder.queue) == 4
    assert recorder.dropped == 46
    monkeypatch.setattr(time, "time", lambda: recorder.previous_at - 600)
    recorder.collect(pipeline=values["pipeline"], context={"build": "other"}, gauges={}, skills=[])
    record = json.loads(recorder.queue[-1])
    assert {"clock_jump", "partial_interval", "mixed_context"} <= set(record["flags"])
    assert all(len(raw) <= storage.MAX_INPUT for raw in recorder.queue)


def test_real_collector_uses_no_snapshot_and_keeps_core_budget(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    monkeypatch.setattr(
        engine, "snapshot", lambda: pytest.fail("diagnostics must not build dashboard")
    )
    engine._record_pipeline_recent("processed", lag_seconds=50, critical=True)
    engine._collect_diagnostics()
    record = json.loads(engine.diagnostics.queue[-1])
    assert record["pipeline"]["critical_histogram"][-1] == 1
    assert record["pipeline"]["critical_lag_max"] == 50
    engine._record_pipeline_recent("processed", lag_seconds=0.1)
    engine._collect_diagnostics()
    second = json.loads(engine.diagnostics.queue[-1])
    assert second["pipeline"]["processed"] == 1
    assert second["pipeline"]["lag_max"] == 0.1
    assert second["pipeline"]["critical_count"] == 0
    assert engine.diagnostics.directory != engine.database.path
    engine.database.close()


@pytest.mark.parametrize(
    "legacy_field",
    ["feature_schema_version", "baseline_version", "risk_mode", "configuration_fingerprint"],
)
@pytest.mark.parametrize("legacy_first", [True, False])
def test_diagnostics_tracks_current_cohort_and_runtime_support(
    settings, monkeypatch, legacy_field, legacy_first
):
    from signal_arcade.intelligence.learning import FEATURE_SCHEMA_VERSION, _challenger_cohort_key
    from signal_arcade.models import (
        ChallengerSkill,
        ChallengerSkillArtifact,
        ChallengerSkillState,
        RiskMode,
    )

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    context = {
        "risk_mode": engine.risk_mode,
        "configuration_fingerprint": engine._configuration_fingerprint(),
        "baseline_version": engine.learning.baseline_version(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }
    legacy_context = {
        **context,
        legacy_field: RiskMode.AGGRESSIVE if legacy_field == "risk_mode" else "legacy",
    }
    artifacts = []
    states = []
    for label, scope in (("current", context), ("legacy", legacy_context)):
        # A newer imported artifact must not replace the current cohort's summary.
        artifact = ChallengerSkillArtifact(
            version=label + "-candidate",
            skill=ChallengerSkill.EXIT,
            **scope,
            created_at=datetime.now(UTC) + timedelta(days=1 if label == "legacy" else 0),
        )
        cohort = _challenger_cohort_key(**scope)
        state = ChallengerSkillState(
            cohort_key=cohort,
            skill=ChallengerSkill.EXIT,
            **scope,
            champion_version=label + "-champion",
            active_version=label + "-champion",
            testing_version=artifact.version,
            common_forward_count=44 if label == "current" else 1,
        )
        artifacts.append(artifact)
        states.append(state)
    if legacy_first:
        artifacts.reverse()
        states.reverse()
    engine.learning.skill_artifacts = {a.version: a for a in artifacts}
    engine.learning.skill_states = {(s.cohort_key, s.skill): s for s in states}
    engine.learning.active_skill_versions = {"exit": "current-champion"}
    monkeypatch.setattr(engine, "snapshot", lambda: pytest.fail("no dashboard work in diagnostics"))
    monkeypatch.setattr(
        engine.database, "save_challenger_skill_state", lambda *_: pytest.fail("read only")
    )
    try:
        assert (
            engine.learning._current_skill_state(ChallengerSkill.EXIT).champion_version
            == "current-champion"
        )
        engine._collect_diagnostics()
        record = json.loads(engine.diagnostics.queue[-1])
        assert len(record["skills"]) == 1
        skill = record["skills"][0]
        assert skill["id"] == identity("current-candidate")
        assert skill["champion"] == skill["active"] == identity("current-champion")
        assert skill["testing"] == identity("current-candidate")
        assert skill["shared"] == 44
        # A durable activation receipt alone cannot claim current runtime authority.
        engine.learning.active_skill_versions.clear()
        engine._collect_diagnostics()
        inactive = json.loads(engine.diagnostics.queue[-1])["skills"][0]
        assert inactive["active"] is None
        assert inactive["champion"] == identity("current-champion")
    finally:
        engine.database.close()


def test_collector_lock_timeout_preserves_pipeline_for_next_interval(settings, monkeypatch):
    import signal_arcade.orchestrator as orchestration

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    clock = [time.monotonic()]
    monkeypatch.setattr(
        orchestration,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0], process_time=time.process_time),
    )
    waits = 0

    async def scenario():
        nonlocal waits
        await engine._event_lock.acquire()
        engine._record_pipeline_recent("processed", lag_seconds=2, critical=True)

        async def next_cycle(_delay):
            nonlocal waits
            waits += 1
            clock[0] += 61
            if waits == 2:
                # A busy core boundary skips collection, without consuming its counters.
                assert engine.diagnostics.dropped == 1
                assert engine.diagnostics.sequence == 0
                assert engine.diagnostics.cursor.serial == 0
                engine._event_lock.release()
                engine._record_pipeline_recent("processed", lag_seconds=0.1)
            elif waits == 3:
                engine.stop_event.set()

        monkeypatch.setattr(engine, "_wait_for_stop", next_cycle)
        await engine._diagnostics_loop()
        assert len(engine.diagnostics.queue) == 1
        record = json.loads(engine.diagnostics.queue[0])
        assert record["pipeline"]["processed"] == 2
        assert record["pipeline"]["critical_count"] == 1
        assert sum(record["pipeline"]["lag_histogram"]) == 2
        assert "recording_gap" in record["flags"]

    try:
        asyncio.run(scenario())
    finally:
        engine.database.close()


def test_export_keysets_keep_equal_timestamp_rows_across_pages(tmp_path):
    store = DiagnosticsStore(tmp_path)
    try:
        # Multiple boots and sequences may share timestamps after fast restarts or a clock jump.
        for index in range(205):
            record = interval(index % 5, boot=f"{index // 5:032x}")
            record["start"], record["end"] = 1_788_600_000, 1_788_600_060
            assert store.append(record)
        minute_rows, event_rows = [], []
        cursor = None
        while page := read_page(tmp_path, tier=0, before=2e9, after=cursor):
            assert len(page) <= 100
            minute_rows.extend(page)
            cursor = tuple(page[-1]["cursor"])
        cursor = None
        while page := read_events(tmp_path, before=2e9, after=cursor):
            assert len(page) <= 100
            event_rows.extend(page)
            cursor = tuple(page[-1]["cursor"])
        assert len(minute_rows) == len(event_rows) == 205
        assert len({tuple(row["cursor"]) for row in minute_rows}) == 205
        assert len({tuple(row["cursor"]) for row in event_rows}) == 205
        assert (
            read_page(tmp_path, tier=1, before=2e9)[0]["record"]["pipeline"]["processed"] == 205 * 9
        )
    finally:
        store.close()


def test_readiness_does_not_erase_last_fit(settings):
    learner, database, _ = training_fixture(settings)
    assert learner.run_next_training()
    last_fit = copy.deepcopy(learner.training_status()["last_fit"])
    learner.request_current_training()
    assert learner.prepare_next_training() is None
    assert learner.training_status()["last_fit"] == last_fit
    assert "fit_seconds" in last_fit["phase_seconds"]
    database.close()


def test_writer_lifecycle_and_duplicate_owner(tmp_path):
    async def scenario():
        recorder = DiagnosticsRecorder(tmp_path)
        await recorder.start()
        other = DiagnosticsRecorder(tmp_path)
        try:
            for _ in range(100):
                if recorder.status()["state"] == "recording":
                    break
                await asyncio.sleep(0.02)
            values = interval()
            recorder.collect(
                pipeline=values["pipeline"], context=values["context"], gauges={}, skills=[]
            )
            await recorder.flush_one(allowed=False)
            assert len(recorder.queue) == 1
            await recorder.flush_one(allowed=True)
            for _ in range(100):
                if recorder.status().get("ranges", {}).get("minute", {}).get("rows") == 1:
                    break
                await asyncio.sleep(0.02)
            assert recorder.status()["ranges"]["minute"]["rows"] == 1
            await other.start()
            for _ in range(100):
                if other.status()["state"] == "unavailable":
                    break
                await asyncio.sleep(0.02)
            assert other.status()["state"] == "unavailable"
        finally:
            await other.stop()
            await recorder.stop()
        assert not recorder.writer.thread.is_alive()

    asyncio.run(scenario())


def test_six_full_skill_summaries_fit_record_budget(tmp_path):
    import random

    rng = random.Random(7)  # noqa: S311 - deterministic synthetic metrics, not credentials
    skills = []
    for index in range(6):
        artifact = SimpleNamespace(
            version=f"version-{index}",
            skill=SimpleNamespace(value="entry"),
            model_family=SimpleNamespace(value="xgboost"),
            qualified=False,
            sample_count=5000,
            training_count=3000,
            validation_count=1000,
            metrics={key: rng.random() for key in PROOF_METRICS},
        )
        item = artifact_summary(artifact)
        item.update(champion="a" * 24, active="b" * 24, testing="c" * 24, shared=500)
        skills.append(item)
    record = interval()
    record["skills"] = skills
    record["context"] = {"build": "d" * 64, "configuration": "e" * 24, "season": "f" * 24}
    store = DiagnosticsStore(tmp_path)
    assert store.append(record)
    assert read_page(tmp_path, tier=0, before=2e9)[0]["record"]["skills"] == skills
    store.close()


def test_authenticated_export_and_separate_reset_budget(settings):
    from fastapi.testclient import TestClient
    from signal_arcade.api import create_app

    app = create_app(settings.model_copy(update={"admin_password": "fixture-password"}))
    engine = app.state.orchestrator
    client = TestClient(app)  # No lifespan: this test starts no providers or background workers.
    store = DiagnosticsStore(engine.diagnostics.directory)
    before = engine.database.storage_capacity_stats()["database_bytes"]
    try:
        store.append(interval())
        assert engine.database.storage_capacity_stats()["database_bytes"] == before
        assert client.get("/api/v1/diagnostics").status_code == 401
        assert client.get("/api/v1/diagnostics/export").status_code == 401
        response = client.get("/api/v1/diagnostics/export", auth=("test", "fixture-password"))
        assert response.status_code == 200
        lines = [json.loads(line) for line in response.text.splitlines()]
        assert lines[0]["type"] == "metadata"
        assert lines[-1]["type"] == "export_complete"
        assert any(line["type"] == "event" for line in lines)
        engine.database.reset_paper_state()
        assert len(read_page(engine.diagnostics.directory, tier=0, before=2e9)) == 1
    finally:
        store.close()
        client.close()
        engine.database.close()


def test_exports_limit_concurrency_and_release_on_disconnect(settings):
    from fastapi import HTTPException
    from signal_arcade.api import create_app

    app = create_app(settings)
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/diagnostics/export"
    )

    async def scenario():
        first, second = await endpoint(), await endpoint()
        await anext(first.body_iterator)
        await anext(second.body_iterator)
        with pytest.raises(HTTPException) as caught:
            await endpoint()
        assert caught.value.status_code == 429
        await first.body_iterator.aclose()
        third = await endpoint()
        await anext(third.body_iterator)
        await third.body_iterator.aclose()
        await second.body_iterator.aclose()
        # Background cleanup is idempotent even after the streaming generator released its slot.
        await first.background()
        fourth = await endpoint()
        fifth = await endpoint()
        with pytest.raises(HTTPException) as caught:
            await endpoint()
        assert caught.value.status_code == 429
        await fourth.background()
        await fifth.background()

    try:
        asyncio.run(scenario())
    finally:
        app.state.orchestrator.database.close()


def test_diagnostics_does_not_change_learning_configuration_identity(settings):
    engine = Orchestrator(settings)
    before = engine._configuration_fingerprint()
    engine.settings = settings.model_copy(
        update={"diagnostics_enabled": not settings.diagnostics_enabled}
    )
    assert engine._configuration_fingerprint() == before
    engine.database.close()


def test_export_header_disconnect_cannot_leak_a_slot(settings):
    from signal_arcade.api import create_app
    from starlette.requests import ClientDisconnect

    app = create_app(settings)
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/diagnostics/export"
    )

    async def disconnected_send(_message):
        raise OSError("client disconnected before headers")

    async def receive():
        return {"type": "http.disconnect"}

    async def scenario():
        # More than the concurrency limit of consecutive early disconnects must remain possible.
        for _ in range(4):
            response = await endpoint()
            with pytest.raises(ClientDisconnect):
                await response(
                    {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, disconnected_send
                )
        first, second = await endpoint(), await endpoint()
        await first.background()
        await second.background()

    try:
        asyncio.run(scenario())
    finally:
        app.state.orchestrator.database.close()


def test_full_operational_interval_and_six_proof_events_fit(tmp_path):
    import random

    rng = random.Random(7)  # noqa: S311 - deterministic synthetic metrics, not credentials
    skills = []
    for _index in range(6):
        skills.append(
            dict(
                id=f"{rng.getrandbits(96):024x}",
                skill="manipulation",
                family="xgboost",
                qualified=False,
                created_at=1788610318.012345,
                counts=[5000, 3000, 1000],
                metrics={key: round(rng.random(), 6) for key in PROOF_METRICS},
                champion=f"{rng.getrandbits(96):024x}",
                active=f"{rng.getrandbits(96):024x}",
                testing=f"{rng.getrandbits(96):024x}",
                shared=500,
            )
        )
    pipeline = {
        key: rng.randint(0, 500000)
        for key in (
            "enqueued",
            "processed",
            "shed",
            "expired",
            "reordered",
            "lag_count",
            "critical_count",
        )
    }
    pipeline.update(
        lag_max=61.12345,
        critical_lag_max=32.12345,
        queue_max=1024,
        lag_histogram=list(range(9)),
        critical_histogram=list(range(9)),
    )
    gauges = {
        key: 12345
        for key in (
            "queue",
            "training_runs",
            "models_published",
            "ai_queue",
            "ai_queue_drops",
            "ai_pending_tokens",
            "coach_busy",
            "coach_error",
            "coach_context_outcomes",
            "coach_retained_reviews",
            "coach_retained_hypotheses",
            "training_discarded",
            "training_errors",
            "outcomes_seen",
            "provider_reconnects",
            "snapshot_age",
            "app_cpu_seconds",
            "database_bytes",
            "database_live_bytes",
            "storage_active",
            "running",
            "workers_healthy",
            "diagnostics_dropped",
            "app_rss_bytes",
        )
    }
    gauges.update(
        paper_equity=dict(
            at=1788610318.12345,
            season="f" * 24,
            currency="USDC",
            decimals=6,
            starting=400000000,
            cash=399000000,
            equity=400100000,
            realized=-20000,
            unrealized=30000,
            excluded=1,
            open_positions=5,
            drawdown=0.002,
        ),
        ai_mode="shadow",
    )
    value = dict(
        boot="a" * 32,
        seq=6000,
        start=1788610318.12345,
        end=1788610378.12345,
        elapsed=60,
        flags=["partial_interval", "recording_gap", "mixed_context"],
        context=dict(
            build="b" * 64,
            version="1.10.5",
            configuration="c" * 24,
            season="d" * 24,
            risk="balanced",
            demo=False,
            learning_mode="shadow",
            profile="e" * 24,
            scope="sampled_at_interval_end",
        ),
        pipeline=pipeline,
        phases={
            key: [60 + index, 123.456789123 / (index + 1), 12.987654321 / (index + 1)]
            for index, key in enumerate(sorted(PHASES))
        },
        gauges=gauges,
        skills=skills,
    )
    value["events"] = [{"kind": "proof", **item} for item in skills]
    recorder = DiagnosticsRecorder(tmp_path)
    for event in value["events"]:
        recorder.event(event)
    recorder.collect(pipeline=pipeline, context=value["context"], gauges=gauges, skills=skills)
    assert len(recorder.queue) == 1 and recorder.dropped == 0
    store = DiagnosticsStore(tmp_path)
    assert store.append(value)
    later = {**value, "seq": 6001, "start": value["end"], "end": value["end"] + 60}
    assert store.append(later)
    assert read_page(tmp_path, tier=0, before=2e9)[0]["record"]["skills"] == skills
    assert len(read_events(tmp_path, before=2e9)) == 12
    assert store.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


@pytest.mark.parametrize("failure", [ValueError, asyncio.CancelledError])
def test_operation_measurement_preserves_failures_and_is_bounded(tmp_path, monkeypatch, failure):
    recorder = DiagnosticsRecorder(tmp_path)
    clock = iter([10.0, 10.25, 11.0, 11.5, 12.0, 12.5])
    monkeypatch.setattr("signal_arcade.diagnostics.time.monotonic", lambda: next(clock))
    with pytest.raises(failure), recorder.measure("event_broker"):
        raise failure()
    with recorder.measure("event_broker"):
        pass
    with recorder.measure("untrusted_phase"):
        pass
    assert recorder.phases == {"event_broker": [2, 0.75, 0.5]}
    assert not recorder.queue and not recorder.events


def test_disabled_operation_measurement_has_no_recording(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path, enabled=False)
    with recorder.measure("event_broker"):
        pass
    assert recorder.phases == {} and not recorder.queue
