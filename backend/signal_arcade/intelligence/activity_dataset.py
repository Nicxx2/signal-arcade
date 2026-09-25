"""Explicit, bounded research snapshots. Never imported by the running trading service."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..models import LearningEvidenceEpisode
from .activity_evidence import MAX_ACTIVITY_EVIDENCE_BYTES
from .learning import _policy_identity_key


class StudyWindow(Protocol):
    """Only the declared read window and its serialized specification reach this reader."""

    @property
    def start(self) -> datetime: ...

    @property
    def end(self) -> datetime: ...

    def model_dump_json(self) -> str: ...


MAX_ROWS = 5000
MAX_PARENT_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 96 * 1024 * 1024
READ_SECONDS = 5.0
DISK_RESERVE_BYTES = 16 * 1024 * 1024


class StudyDataset(BaseModel):
    """Exact parent JSON plus optional companions, from one SQLite read transaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["activity-study-dataset-v1"] = "activity-study-dataset-v1"
    spec_sha256: str
    as_of: datetime
    source_schema: int
    parents: list[str] = Field(max_length=MAX_ROWS)
    identities: dict[str, tuple[str, str]]
    companions: dict[str, str]
    pruned_through: str | None
    metadata_rows_read: int = Field(ge=0, le=MAX_ROWS)
    parent_bytes: int = Field(ge=0, le=MAX_PARENT_BYTES)


def spec_digest(study: StudyWindow) -> str:
    return hashlib.sha256(study.model_dump_json().encode()).hexdigest()


def aware_clock(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("study data contains a naive clock")
    return result


def extract_study(
    path: Path, study: StudyWindow, *, max_parent_bytes: int = MAX_PARENT_BYTES
) -> StudyDataset:
    """Read only the declared period; persistent identity receipts protect earlier entries.

    ISO offsets are not lexically chronological. The index supplies a deliberately broad
    calendar envelope; julianday is only a coarse filter with a one-second rounding margin.
    Python aware instants decide exact membership. Neither SQL order nor float time breaks ties.
    """
    if not 0 < max_parent_bytes <= MAX_PARENT_BYTES:
        raise ValueError("invalid parent byte budget")
    deadline = time.monotonic() + READ_SECONDS

    def check_budget() -> None:
        if time.monotonic() > deadline:
            raise ValueError("study read budget exceeded; no partial cohort accepted")

    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=0.1)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, min(max_parent_bytes, 8 * 1024 * 1024))
        connection.execute("PRAGMA cache_size=-1024")
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 500)
        connection.execute("BEGIN")
        # Establish the snapshot before recording its observation clock. A later read must
        # not make the snapshot appear to contain outcomes it could not yet have observed.
        schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        as_of = datetime.now(UTC)
        watermark = connection.execute(
            "SELECT value_json FROM settings WHERE key='coach_policy_pruned_through'"
        ).fetchone()
        has_companions = (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='learning_activity_policy'"
            ).fetchone()
            is not None
        )
        # Python accepts offsets beyond SQLite's parser range. Normalize query parameters
        # even though source-row clocks still use the padded filter and exact Python check.
        start_utc, end_utc = study.start.astimezone(UTC), study.end.astimezone(UTC)
        lower = (start_utc - timedelta(days=1)).date().isoformat()
        upper = (end_utc + timedelta(days=2)).date().isoformat()
        cursor = connection.execute(
            "SELECT episode_id,created_at FROM learning_evidence_episodes "
            "INDEXED BY idx_learning_evidence_lane_time "
            "WHERE lane='policy' AND created_at>=? AND created_at<? "
            "AND (julianday(created_at) IS NULL OR "
            "julianday(created_at) BETWEEN julianday(?) AND julianday(?)) LIMIT ?",
            (
                lower,
                upper,
                (start_utc - timedelta(seconds=1)).isoformat(),
                (end_utc + timedelta(seconds=1)).isoformat(),
                MAX_ROWS + 1,
            ),
        )
        metadata: list[tuple[datetime, str]] = []
        scanned = 0
        for episode_id, clock in cursor:
            check_budget()
            scanned += 1
            if scanned > MAX_ROWS:
                raise ValueError("study row budget exceeded; no partial cohort accepted")
            instant = aware_clock(str(clock))
            if study.start <= instant < study.end and instant <= as_of:
                metadata.append((instant, str(episode_id)))
        parents: list[str] = []
        identities: dict[str, tuple[str, str]] = {}
        companions: dict[str, str] = {}
        byte_count = 0
        for instant, episode_id in sorted(metadata):
            check_budget()
            payload = str(
                connection.execute(
                    "SELECT record_json FROM learning_evidence_episodes WHERE episode_id=?",
                    (episode_id,),
                ).fetchone()[0]
            )
            byte_count += len(payload.encode())
            if byte_count > max_parent_bytes:
                raise ValueError("study parent byte budget exceeded; no partial cohort accepted")
            parent = LearningEvidenceEpisode.model_validate_json(payload)
            if (
                parent.episode_id != episode_id
                or parent.lane.value != "policy"
                or parent.created_at != instant
                or parent.entry_at != instant
            ):
                raise ValueError("study parent identity/clock disagrees with indexed metadata")
            parents.append(payload)
            key = _policy_identity_key(parent)
            receipt = connection.execute(
                "SELECT first_entry_at,first_episode_id FROM learning_policy_identities "
                "WHERE identity_key=?",
                (key,),
            ).fetchone()
            if receipt is not None:
                identities[key] = (str(receipt[0]), str(receipt[1]))
            if has_companions:
                data = connection.execute(
                    "SELECT CASE WHEN length(CAST(record_json AS BLOB))<=? "
                    "THEN record_json ELSE '{}' END FROM learning_activity_policy "
                    "WHERE parent_id=?",
                    (MAX_ACTIVITY_EVIDENCE_BYTES, episode_id),
                ).fetchone()
                if data is not None:
                    companions[episode_id] = str(data[0])
        check_budget()
        return StudyDataset(
            spec_sha256=spec_digest(study),
            as_of=as_of,
            source_schema=schema,
            parents=parents,
            identities=identities,
            companions=companions,
            pruned_through=None if watermark is None else str(watermark[0]),
            metadata_rows_read=scanned,
            parent_bytes=byte_count,
        )
    finally:
        connection.close()


def validate_dataset(
    data: StudyDataset,
    study: StudyWindow,
) -> tuple[list[LearningEvidenceEpisode], list[str]]:
    """Revalidate imported data; absence of a recorded retention overlap is not a census."""
    if data.spec_sha256 != spec_digest(study) or data.as_of.utcoffset() is None:
        raise ValueError("dataset specification or observation clock mismatch")
    if data.parent_bytes != sum(len(payload.encode()) for payload in data.parents):
        raise ValueError("dataset parent byte count mismatch")
    if data.metadata_rows_read < len(data.parents):
        raise ValueError("dataset metadata count mismatch")
    rows = [LearningEvidenceEpisode.model_validate_json(payload) for payload in data.parents]
    ids = {row.episode_id for row in rows}
    by_identity: dict[str, list[LearningEvidenceEpisode]] = {}
    for row in rows:
        by_identity.setdefault(_policy_identity_key(row), []).append(row)
    keys = by_identity.keys()
    if (
        len(ids) != len(rows)
        or not data.companions.keys() <= ids
        or not data.identities.keys() <= keys
    ):
        raise ValueError("dataset contains duplicate or unrelated records")
    for row in rows:
        if (
            row.entry_at.utcoffset() is None
            or row.created_at != row.entry_at
            or row.lane.value != "policy"
            or not study.start <= row.entry_at < study.end
            or row.entry_at > data.as_of
        ):
            raise ValueError("dataset contains an out-of-scope parent")
    issues: set[str] = set()
    if data.source_schema != 16:
        issues.add("unverified_source_schema")
    for key in keys:
        receipt = data.identities.get(key)
        try:
            if receipt is None or not receipt[1]:
                raise ValueError("missing receipt")
            first_at = aware_clock(receipt[0])
            matching = by_identity[key]
            if any((first_at, receipt[1]) > (row.entry_at, row.episode_id) for row in matching):
                raise ValueError("identity reservation is later than an existing opportunity")
            if study.start <= first_at < study.end and receipt[1] not in ids:
                issues.add("original_policy_parent_missing")
            if receipt[1] in ids and not any(
                row.episode_id == receipt[1] and row.entry_at == first_at for row in matching
            ):
                raise ValueError("identity reservation disagrees with its original parent")
        except ValueError:
            issues.add("missing_or_invalid_policy_identity")
    if data.pruned_through is not None:
        try:
            watermark = json.loads(data.pruned_through)
            if (
                not isinstance(watermark, list)
                or len(watermark) != 2
                or not all(isinstance(item, str) and item for item in watermark)
            ):
                raise ValueError("invalid watermark")
            # The source watermark uses lexical ordering. Add the maximum ISO offset span
            # before declaring it safely before the study, including mixed-offset fixtures.
            if aware_clock(watermark[0]) + timedelta(days=2) >= study.start:
                issues.add("retention_may_overlap_study")
        except (ValueError, TypeError):
            issues.add("invalid_retention_watermark")
    return rows, sorted(issues)


def write_dataset(path: Path, data: StudyDataset, *, source: Path | None = None) -> None:
    """Publish an entire private bundle atomically, without replacing an existing path."""
    target = path.resolve()
    if source is not None:
        source_path = source.resolve()
        if target in {
            Path(str(source_path) + suffix) for suffix in ("", "-wal", "-shm", "-journal")
        }:
            raise ValueError("dataset destination aliases the source database")
    payload = data.model_dump_json().encode()
    envelope = json.dumps(
        {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "payload": payload.decode(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    if len(envelope) > MAX_BUNDLE_BYTES:
        raise ValueError("dataset output byte budget exceeded")
    if target.exists() or path.is_symlink():
        raise FileExistsError("dataset destination already exists")
    if shutil.disk_usage(target.parent).free < len(envelope) + DISK_RESERVE_BYTES:
        raise OSError("insufficient free space for bounded study dataset")
    descriptor, temporary = tempfile.mkstemp(prefix=".activity-study-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(envelope)
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory hard link is exclusive and atomic on supported local filesystems.
        # If unsupported, fail without falling back to an overwrite or partial final file.
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_dataset(path: Path, study: StudyWindow) -> StudyDataset:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("dataset input byte budget exceeded")
    envelope = json.loads(raw)
    if not isinstance(envelope, dict) or set(envelope) != {"sha256", "payload"}:
        raise ValueError("invalid dataset envelope")
    payload = envelope["payload"]
    if (
        not isinstance(payload, str)
        or hashlib.sha256(payload.encode()).hexdigest() != envelope["sha256"]
    ):
        raise ValueError("dataset digest mismatch")
    data = StudyDataset.model_validate_json(payload)
    validate_dataset(data, study)
    return data
