"""Bounded study extraction must not turn a partial population into favorable evidence."""

import json
import sqlite3
from datetime import timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from signal_arcade.intelligence import activity_dataset as dataset
from signal_arcade.intelligence.activity_research import evaluate_activity, evaluate_dataset
from signal_arcade.intelligence.learning import _policy_identity
from test_activity_research import cohort as shared_cohort

cohort = shared_cohort


def save(db, parent, **updates):
    row = parent.model_copy(deep=True, update=updates)
    db.save_learning_evidence_episode(row)
    db.remember_policy_identities([_policy_identity(row)])
    return row


def test_indexed_period_does_not_materialize_large_old_history(cohort):
    db, _, parent, spec = cohort
    old = (spec.start - timedelta(days=8)).isoformat()
    # Deliberately invalid old parent models prove that unrelated history is not parsed.
    with db._conn:
        db._conn.executemany(
            "INSERT INTO learning_evidence_episodes VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    f"old{i}",
                    f"old{i}",
                    "policy",
                    f"old{i}",
                    f"old{i}",
                    old,
                    "pending" if i % 2 else "complete",
                    "{}",
                )
                for i in range(5001)
            ],
        )
    before = db._conn.total_changes
    result = dataset.extract_study(db.path, spec)
    rows, issues = dataset.validate_dataset(result, spec)
    assert [row.episode_id for row in rows] == [parent.episode_id]
    assert result.metadata_rows_read == 1
    assert not issues
    assert db._conn.total_changes == before


@pytest.mark.parametrize("offset", [-23, -7, 0, 12, 23])
def test_exact_time_boundaries_with_offsets_and_submilliseconds(cohort, offset):
    db, _, parent, spec = cohort
    tz = timezone(timedelta(hours=offset))
    clocks = [
        spec.start - timedelta(microseconds=1),
        spec.start,
        spec.end - timedelta(microseconds=1),
        spec.end,
    ]
    # Put the whole study in the past so no endpoint is excluded as future evidence.
    spec = spec.model_copy(
        update={
            "start": spec.start - timedelta(days=1),
            "end": spec.end - timedelta(days=1),
            "frozen_at": spec.frozen_at - timedelta(days=1),
            "outcome_cutoff": spec.outcome_cutoff - timedelta(days=1),
        }
    )
    for i, clock in enumerate(clocks):
        stamp = (clock - timedelta(days=1)).astimezone(tz)
        save(
            db,
            parent,
            episode_id=f"edge{i}",
            idempotency_key=f"edge{i}",
            trajectory_key=f"edge{i}",
            mint=f"edge{i}",
            created_at=stamp,
            entry_at=stamp,
        )
    result = dataset.extract_study(db.path, spec)
    rows, issues = dataset.validate_dataset(result, spec)
    assert [row.episode_id for row in rows] == ["edge1", "edge2"]
    assert not issues


@pytest.mark.parametrize("offset", [-23, -15, 15, 23])
def test_study_clock_offsets_outside_sqlite_range_preserve_the_cohort(cohort, offset):
    db, _, parent, spec = cohort
    tz = timezone(timedelta(hours=offset))
    shifted = type(spec).model_validate(
        {
            **spec.model_dump(),
            **{
                name: getattr(spec, name).astimezone(tz)
                for name in ("frozen_at", "start", "end", "outcome_cutoff")
            },
        }
    )
    result = dataset.extract_study(db.path, shifted)
    rows, issues = dataset.validate_dataset(result, shifted)
    assert [row.episode_id for row in rows] == [parent.episode_id]
    assert not issues


@pytest.mark.parametrize("failure", ["rows", "time", "bytes", "clock"])
def test_budgets_and_metadata_mismatch_abort_without_partial_data(cohort, monkeypatch, failure):
    db, _, parent, spec = cohort
    if failure == "rows":
        monkeypatch.setattr(dataset, "MAX_ROWS", 0)
    elif failure == "time":
        monkeypatch.setattr(dataset, "READ_SECONDS", -1)
    elif failure == "clock":
        changed = parent.model_copy(update={"entry_at": parent.entry_at + timedelta(seconds=1)})
        with db._conn:
            db._conn.execute(
                "UPDATE learning_evidence_episodes SET record_json=?", (changed.model_dump_json(),)
            )
    with pytest.raises((ValueError, sqlite3.OperationalError, sqlite3.DataError)):
        dataset.extract_study(
            db.path, spec, max_parent_bytes=1024 if failure == "bytes" else dataset.MAX_PARENT_BYTES
        )


def test_concurrent_checkpoint_write_cannot_mix_snapshot_generations(cohort, monkeypatch):
    db, _, parent, spec = cohort
    original_connect = sqlite3.connect
    changed = parent.model_copy(deep=True, update={"symbol": "concurrent writer"})

    class ConcurrentReader(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("SELECT record_json FROM learning_evidence_episodes"):
                db.save_learning_evidence_episode(changed)
            return super().execute(sql, parameters)

    monkeypatch.setattr(
        dataset.sqlite3,
        "connect",
        lambda *a, **kw: original_connect(
            *a,
            **kw,
            factory=ConcurrentReader,
        ),
    )
    result = dataset.extract_study(db.path, spec)
    assert result.parents == [parent.model_dump_json()]
    assert (
        db._conn.execute("SELECT record_json FROM learning_evidence_episodes").fetchone()[0]
        == changed.model_dump_json()
    )


def test_busy_source_defers_without_writing(tmp_path, cohort):
    db, _, _, spec = cohort
    copy = tmp_path / "busy.sqlite"
    target = sqlite3.connect(copy)
    db._conn.backup(target)  # Tiny disposable fixture only.
    target.execute("PRAGMA journal_mode=DELETE")
    target.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            dataset.extract_study(copy, spec)
    finally:
        target.rollback()
        target.close()


def test_bundle_roundtrip_digest_wrong_spec_and_partial_output(cohort, tmp_path):
    db, _, _, spec = cohort
    data = dataset.extract_study(db.path, spec)
    path = tmp_path / "study.private.json"
    dataset.write_dataset(path, data, source=db.path)
    assert dataset.load_dataset(path, spec) == data
    with pytest.raises(FileExistsError):
        dataset.write_dataset(path, data)
    with pytest.raises(ValueError, match="mismatch"):
        dataset.load_dataset(path, spec.model_copy(update={"fee_bps": spec.fee_bps + 1}))
    envelope = json.loads(path.read_text())
    envelope["payload"] += " "
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="digest"):
        dataset.load_dataset(path, spec)
    path.write_text('{"sha256":')
    with pytest.raises(ValueError):
        dataset.load_dataset(path, spec)


@pytest.mark.parametrize("failure", ["disk", "output_cap", "link", "fsync", "race"])
def test_failed_export_never_leaves_partial_final_or_clobbers_another_file(
    cohort,
    tmp_path,
    monkeypatch,
    failure,
):
    db, _, _, spec = cohort
    data = dataset.extract_study(db.path, spec)
    path = tmp_path / "study.private.json"
    if failure == "disk":
        monkeypatch.setattr(dataset.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    elif failure == "output_cap":
        monkeypatch.setattr(dataset, "MAX_BUNDLE_BYTES", 10)
    else:

        def fail(*args):
            if failure == "race":
                path.write_text("someone else's file")
            raise OSError("simulated interrupted or unsupported publication")

        monkeypatch.setattr(dataset.os, "fsync" if failure == "fsync" else "link", fail)
    with pytest.raises((ValueError, OSError)):
        dataset.write_dataset(path, data, source=db.path)
    assert list(tmp_path.glob(".activity-study-*")) == []
    if failure == "race":
        assert path.read_text() == "someone else's file"
    else:
        assert not path.exists()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_export_never_overwrites_database_or_sidecars(cohort, suffix):
    db, _, _, spec = cohort
    data = dataset.extract_study(db.path, spec)
    with pytest.raises(ValueError, match="aliases"):
        dataset.write_dataset(Path(str(db.path) + suffix), data, source=db.path)


@pytest.mark.parametrize(
    "receipt",
    [
        None,
        ("", ""),
        ("not-a-time", "old"),
        ("2026-09-20T12:00:00", "old"),
        ("2099-01-01T00:00:00Z", "future"),
    ],
)
def test_identity_gaps_are_explicit_and_never_qualify(cohort, receipt):
    db, _, parent, spec = cohort
    data = dataset.extract_study(db.path, spec)
    key = _policy_identity(parent)[0]
    data = data.model_copy(update={"identities": {} if receipt is None else {key: receipt}})
    report = evaluate_dataset(data, spec)
    assert "missing_or_invalid_policy_identity" in report["dataset_completeness_issues"]
    assert not report["sufficient_for_economic_screen"]
    assert not report["economic_screen_positive"]
    assert not report["activation_allowed"]


@pytest.mark.parametrize(
    "watermark,expected",
    [
        (None, []),
        ('["2026-09-01T00:00:00Z","old"]', []),
        ('["2026-09-20T00:00:00Z","possibly-recent"]', ["retention_may_overlap_study"]),
        ('["2026-09-21T00:00:00Z","recent"]', ["retention_may_overlap_study"]),
        ("{}", ["invalid_retention_watermark"]),
        ('["2026-09-01T00:00:00","naive"]', ["invalid_retention_watermark"]),
    ],
)
def test_retention_overlap_is_conservative_and_reported(cohort, watermark, expected):
    db, _, _, spec = cohort
    data = dataset.extract_study(db.path, spec).model_copy(update={"pruned_through": watermark})
    _, issues = dataset.validate_dataset(data, spec)
    assert issues == expected


def test_scoped_reader_matches_full_native_selection_with_prior_identities(cohort):
    db, _, parent, spec = cohort
    # A first entry before the study prevents a later attempt inside it from qualifying.
    prior = save(
        db,
        parent,
        episode_id="prior",
        idempotency_key="prior",
        trajectory_key="prior",
        mint="repeated",
        created_at=spec.start - timedelta(seconds=1),
        entry_at=spec.start - timedelta(seconds=1),
    )
    save(
        db,
        parent,
        episode_id="retry",
        idempotency_key="retry",
        trajectory_key="retry",
        mint="repeated",
    )
    # Same instant with a different offset sorts by episode ID, not its text timestamp.
    stamp = parent.entry_at.astimezone(timezone(timedelta(hours=8)))
    save(
        db,
        parent,
        episode_id="tie-z",
        idempotency_key="tie-z",
        trajectory_key="tie-z",
        mint="tie",
        created_at=stamp,
        entry_at=stamp,
        season_id="other-season",
    )
    save(
        db, parent, episode_id="tie-a", idempotency_key="tie-a", trajectory_key="tie-a", mint="tie"
    )
    # Foreign fees/profile/venue are filtered after native selection, not before it.
    save(
        db,
        parent,
        episode_id="different-fee",
        idempotency_key="different-fee",
        trajectory_key="different-fee",
        mint="foreign",
        fee_bps=parent.fee_bps + 1,
    )
    extracted = dataset.extract_study(db.path, spec)
    all_rows = db.list_learning_evidence_episodes()
    full = evaluate_activity(
        spec,
        all_rows,
        db.policy_identities({_policy_identity(row)[0] for row in all_rows}),
        extracted.companions,
        as_of=extracted.as_of,
    )
    scoped = evaluate_dataset(extracted, spec)
    assert full["dataset_sha256"] == scoped["dataset_sha256"]
    assert full["counts"] == scoped["counts"]
    assert scoped["counts"]["opportunities"] == 2
    assert not scoped["dataset_completeness_issues"]
    # Once the old parent is pruned, the persistent receipt still protects this result.
    with db._conn:
        db._conn.execute(
            "DELETE FROM learning_evidence_episodes WHERE episode_id=?", (prior.episode_id,)
        )
    assert (
        evaluate_dataset(dataset.extract_study(db.path, spec), spec)["counts"] == scoped["counts"]
    )


def test_missing_original_inside_study_is_not_replaced_by_retry(cohort):
    db, _, parent, spec = cohort
    save(
        db,
        parent,
        episode_id="retry",
        idempotency_key="retry",
        trajectory_key="retry",
        created_at=parent.entry_at + timedelta(seconds=1),
        entry_at=parent.entry_at + timedelta(seconds=1),
    )
    with db._conn:
        db._conn.execute(
            "DELETE FROM learning_evidence_episodes WHERE episode_id=?", (parent.episode_id,)
        )
    report = evaluate_dataset(dataset.extract_study(db.path, spec), spec)
    assert report["counts"] == {}
    assert "original_policy_parent_missing" in report["dataset_completeness_issues"]


def test_native_cap_applies_before_exact_context_filter(cohort):
    db, _, parent, spec = cohort
    # One matching first entry followed by 1,000 eligible foreign-fee mints: the
    # research tool must not rescue the first by applying its fee filter early.
    for i in range(1000):
        save(
            db,
            parent,
            episode_id=f"later-{i:04}",
            idempotency_key=f"later-{i:04}",
            trajectory_key=f"later-{i:04}",
            mint=f"later-{i:04}",
            created_at=parent.entry_at + timedelta(seconds=1),
            entry_at=parent.entry_at + timedelta(seconds=1),
            fee_bps=parent.fee_bps + 1,
        )
    data = dataset.extract_study(db.path, spec)
    report = evaluate_dataset(data, spec)
    assert report["study_selection_may_be_truncated"]
    assert report["counts"] == {"context_excluded": 1000}
    assert not report["sufficient_for_economic_screen"]


def test_cli_export_then_offline_evaluation_produce_identical_reports(
    cohort,
    tmp_path,
    monkeypatch,
    capsys,
):
    from signal_arcade.intelligence.activity_research import main

    db, _, _, spec = cohort
    spec_path, output = tmp_path / "spec.json", tmp_path / "private-study.json"
    spec_path.write_text(spec.model_dump_json())
    monkeypatch.setattr(
        "sys.argv", ["activity_research", str(db.path), str(spec_path), "--export", str(output)]
    )
    main()
    first = json.loads(capsys.readouterr().out)
    monkeypatch.setattr(
        "sys.argv", ["activity_research", str(output), str(spec_path), "--from-bundle"]
    )
    main()
    assert json.loads(capsys.readouterr().out) == first
    assert not first["activation_allowed"]


def test_completeness_issue_blocks_an_otherwise_positive_economic_screen(cohort):
    from test_activity_research import outcome, pattern

    db, _, parent, spec = cohort
    original = dataset.extract_study(db.path, spec)
    parents, identities, companions = [], {}, {}
    for i in range(200):
        row = parent.model_copy(deep=True, update={"episode_id": str(i), "mint": str(i)})
        record = pattern(row)
        outcome(row, -0.5 if i < 100 else 0.01)
        if i >= 100:
            record.metrics["buy_ratio_5m"] = (0.5, 1.0, 0, None)
        parents.append(row.model_dump_json())
        identity = _policy_identity(row)
        identities[identity[0]] = identity[1:]
        companions[row.episode_id] = record.model_dump_json()
    good = original.model_copy(
        update={
            "parents": parents,
            "identities": identities,
            "companions": companions,
            "metadata_rows_read": len(parents),
            "parent_bytes": sum(len(p.encode()) for p in parents),
            "as_of": spec.outcome_cutoff,
        }
    )
    assert evaluate_dataset(good, spec)["economic_screen_positive"]
    unsafe = good.model_copy(update={"identities": {}})
    report = evaluate_dataset(unsafe, spec)
    assert not report["economic_screen_positive"]
    assert "missing_or_invalid_policy_identity" in report["screen_blockers"]
