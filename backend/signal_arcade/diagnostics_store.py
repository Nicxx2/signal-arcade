"""Bounded, disposable operational history. Never opens the trading database.

The writer runs in a dedicated I/O thread. Only short, detached reads are used by exports.
All units are seconds/bytes; distributions contain counts, not averaged percentiles.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sqlite3
import stat
import time
import zlib
from pathlib import Path
from typing import Any

from .diagnostics_schema import PROOF_METRICS

SCHEMA = 1
BUDGET = 512 * 1024 * 1024
PAUSE_BYTES = 448 * 1024 * 1024
CLEAN_BYTES = 384 * 1024 * 1024
RESERVE_BYTES = 8 * 1024 * 1024
RESUME_BYTES = 416 * 1024 * 1024
MIN_FREE_BYTES = 512 * 1024 * 1024
MINUTE_ROWS = 43_200
HOUR_ROWS = 8_760
EVENT_ROWS = 100_000
MAX_INPUT = 32_768
MAX_PAYLOAD = 3_584
MAX_EVENT_PAYLOAD = 768
LAG_BOUNDS = [0.1, 0.25, 0.5, 1, 2, 5, 10, 30]
COUNTERS = ("enqueued", "processed", "shed", "expired", "reordered", "lag_count", "critical_count")
MAXIMA = ("lag_max", "critical_lag_max", "queue_max")


def _pack_summary(value: dict[str, Any]) -> dict[str, Any]:
    if "metrics" not in value:
        return value
    return {
        **{key: item for key, item in value.items() if key != "metrics"},
        "metric_values": [
            [index, value["metrics"][key]]
            for index, key in enumerate(PROOF_METRICS)
            if key in value["metrics"]
        ],
    }


def _unpack_summary(value: dict[str, Any]) -> dict[str, Any]:
    if "metric_values" not in value:
        return value
    metrics = {}
    for index, item in value["metric_values"]:
        if type(index) is not int or not 0 <= index < len(PROOF_METRICS):
            raise ValueError("invalid_record")
        key = PROOF_METRICS[index]
        if key in metrics:
            raise ValueError("invalid_record")
        metrics[key] = item
    return {
        **{key: item for key, item in value.items() if key != "metric_values"},
        "metrics": metrics,
    }


def encode(value: Any, *, max_payload: int = MAX_PAYLOAD) -> bytes:
    if isinstance(value, dict):
        value = _pack_summary(value)
        if "skills" in value:
            value = {**value, "skills": [_pack_summary(item) for item in value["skills"]]}
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(raw) > MAX_INPUT:
        raise ValueError("record_too_large")
    packed = zlib.compress(raw, 1)
    if len(packed) > max_payload:
        raise ValueError("record_too_large")
    return packed


def decode(value: bytes) -> Any:
    if len(value) > MAX_PAYLOAD:
        raise ValueError("invalid_record")
    reader = zlib.decompressobj()
    try:
        raw = reader.decompress(value, MAX_INPUT + 1)
    except zlib.error as exc:
        raise ValueError("invalid_record") from exc
    if len(raw) > MAX_INPUT or not reader.eof:
        raise ValueError("invalid_record")
    decoded = json.loads(raw)
    try:
        if isinstance(decoded, dict):
            decoded = _unpack_summary(decoded)
            if "skills" in decoded:
                decoded = {
                    **decoded,
                    "skills": [_unpack_summary(item) for item in decoded["skills"]],
                }
        return decoded
    except (IndexError, TypeError, KeyError) as exc:
        raise ValueError("invalid_record") from exc


def owned_bytes(directory: Path) -> int:
    # No recursion and no removal of unknown files. Extra files consume the same allowance.
    total = 0
    with os.scandir(directory) as entries:
        for index, item in enumerate(entries):
            info = item.stat(follow_symlinks=False)
            if index >= 16 or not stat.S_ISREG(info.st_mode):
                raise ValueError("unexpected_diagnostic_files")
            total += info.st_size
    return total


def merge_hour(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    result = dict(current)
    result["start"] = min(previous["start"], current["start"])
    result["end"] = max(previous["end"], current["end"])
    result["elapsed"] = previous["elapsed"] + current["elapsed"]
    result["intervals"] = previous.get("intervals", 1) + 1
    if previous.get("omitted_events") or current.get("omitted_events"):
        result["omitted_events"] = previous.get("omitted_events", 0) + current.get(
            "omitted_events", 0
        )
    flags = set(previous["flags"]) | set(current["flags"])
    if previous["context"] != current["context"]:
        flags.add("mixed_context")
    if previous["boot"] != current["boot"]:
        flags.add("multiple_boots")
    if current["start"] - previous["end"] > 5:
        flags.add("recording_gap")
    result["flags"] = sorted(flags)
    pipeline = dict(current["pipeline"])
    for key in COUNTERS:
        pipeline[key] = previous["pipeline"].get(key, 0) + pipeline.get(key, 0)
    for key in MAXIMA:
        pipeline[key] = max(previous["pipeline"].get(key, 0), pipeline.get(key, 0))
    for key in ("lag_histogram", "critical_histogram"):
        pipeline[key] = [
            a + b
            for a, b in zip(
                previous["pipeline"].get(key, [0] * 9), pipeline.get(key, [0] * 9), strict=True
            )
        ]
    result["pipeline"] = pipeline
    phases = {key: list(value) for key, value in previous["phases"].items()}
    for key, value in current["phases"].items():
        old = phases.setdefault(key, [0, 0.0, 0.0])
        phases[key] = [old[0] + value[0], old[1] + value[1], max(old[2], value[2])]
    result["phases"] = phases
    return result


class DiagnosticsStore:
    def __init__(self, directory: Path) -> None:
        if directory.is_symlink():
            raise ValueError("unexpected_diagnostic_files")
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.path = directory / "history.sqlite3"
        self.paused = False
        self.writes = 0
        self.early_evictions = 0
        self.retention_at: float | None = None
        if owned_bytes(directory) >= PAUSE_BYTES:
            self.paused = True
        self.connection = sqlite3.connect(self.path, timeout=0.02)
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            tables = self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' LIMIT 8"
            ).fetchall()
            if version not in (0, SCHEMA) or (version == 0 and tables):
                raise ValueError("unsupported_schema")
            if version == SCHEMA and not {"intervals", "events", "boots", "metadata"}.issubset(
                {row[0] for row in tables}
            ):
                raise ValueError("unsupported_schema")
            # Check compatibility before any persistent PRAGMA/schema changes.
            self.connection.execute("PRAGMA busy_timeout=20")
            self.connection.execute("PRAGMA cache_size=-1024")
            self.connection.execute("PRAGMA temp_store=MEMORY")
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.execute("PRAGMA wal_autocheckpoint=128")
            self.connection.execute("PRAGMA journal_size_limit=4194304")
            page_size = self.connection.execute("PRAGMA page_size").fetchone()[0]
            self.page_size = int(page_size)
            self.connection.execute(f"PRAGMA max_page_count={CLEAN_BYTES // page_size}")
            if version == 0:
                self.connection.executescript("""
                    CREATE TABLE intervals (
                        tier INTEGER NOT NULL, boot TEXT NOT NULL, seq INTEGER NOT NULL,
                        at REAL NOT NULL, until_at REAL NOT NULL, payload BLOB NOT NULL,
                        PRIMARY KEY(tier, boot, seq)
                    );
                    CREATE INDEX interval_time ON intervals(tier, at, boot, seq);
                    CREATE INDEX interval_end ON intervals(tier, until_at);
                    CREATE TABLE events (
                        boot TEXT NOT NULL, seq INTEGER NOT NULL, item INTEGER NOT NULL,
                        at REAL NOT NULL, payload BLOB NOT NULL,
                        PRIMARY KEY(boot, seq, item)
                    );
                    CREATE INDEX event_time ON events(at, boot, seq, item);
                    CREATE TABLE boots (
                        boot TEXT PRIMARY KEY, seq INTEGER NOT NULL, ended REAL NOT NULL
                    );
                    CREATE INDEX boot_end ON boots(ended);
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value REAL NOT NULL);
                    PRAGMA user_version=1;
                """)
            meta = dict(self.connection.execute("SELECT key,value FROM metadata"))
            self.early_evictions = int(meta.get("early_evictions", 0))
            self.retention_at = meta.get("retention_at")
            self.retired_boot_before = meta.get("retired_boot_before", -1.0)
            self.boot_count = self.connection.execute("SELECT count(*) FROM boots").fetchone()[0]
            self.counts = dict(
                self.connection.execute("SELECT tier,count(*) FROM intervals GROUP BY tier")
            )
            self.event_count = self.connection.execute("SELECT count(*) FROM events").fetchone()[0]
        except BaseException:
            self.connection.close()
            raise

    def _checkpoint(self) -> None:
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def append(self, record: dict[str, Any]) -> bool:
        started = time.monotonic()
        boot, seq = record["boot"], record["seq"]
        if (
            not isinstance(boot, str)
            or len(boot) != 32
            or any(c not in "0123456789abcdef" for c in boot)
        ):
            raise ValueError("invalid_identity")
        if type(seq) is not int or not 0 <= seq < 2**53:
            raise ValueError("invalid_identity")
        for key in ("start", "end", "elapsed"):
            if not isinstance(record[key], (int, float)) or not math.isfinite(record[key]):
                raise ValueError("invalid_time")
        if not 0 <= record["elapsed"] <= 86_400 or record["end"] < 0:
            raise ValueError("invalid_time")
        previous_boot = self.connection.execute(
            "SELECT seq,ended FROM boots WHERE boot=?", (boot,)
        ).fetchone()
        if previous_boot and seq <= previous_boot[0]:
            return True
        if previous_boot is None and record["end"] <= self.retired_boot_before:
            raise ValueError("expired_boot_identity")
        events = record.get("events", [])
        if not isinstance(events, list) or len(events) > 8:
            raise ValueError("too_many_events")
        interval = {key: value for key, value in record.items() if key != "events"}
        if seq > (previous_boot[0] + 1 if previous_boot else 0):
            interval["flags"] = sorted(set(interval["flags"]) | {"recording_gap"})
        packed_events = []
        omitted_events = 0
        for event in events:
            try:
                packed_events.append(encode(event, max_payload=MAX_EVENT_PAYLOAD))
            except (ValueError, TypeError):
                omitted_events += 1
        if omitted_events:
            interval["flags"] = sorted(set(interval["flags"]) | {"event_omitted"})
            interval["omitted_events"] = omitted_events
        packed = encode(interval)
        usage = owned_bytes(self.directory)
        if usage >= (RESUME_BYTES if self.paused else PAUSE_BYTES):
            self._checkpoint()
            usage = owned_bytes(self.directory)
            if usage >= (RESUME_BYTES if self.paused else PAUSE_BYTES):
                self.paused = True
                return False
        if shutil.disk_usage(self.directory).free < MIN_FREE_BYTES:
            self.paused = True
            return False
        self.paused = False
        until_at = record["end"]
        # Monotonic elapsed bounds retention advancement after a clock jump. Row limits still
        # apply during backward clocks or long downtime; no healthy intervals are backfilled.
        retention = (
            until_at
            if self.retention_at is None
            else min(until_at, self.retention_at + record["elapsed"] + 5)
        )
        retention = max(self.retention_at or 0, retention)
        hour = int(until_at // 3600)
        early = self.early_evictions
        counts = dict(self.counts)
        event_count = self.event_count
        boot_count = self.boot_count + int(previous_boot is None)
        retired_boot_before = self.retired_boot_before
        reclaim_detail = False
        if usage >= CLEAN_BYTES - RESERVE_BYTES:
            pages = self.connection.execute("PRAGMA page_count").fetchone()[0]
            reusable = self.connection.execute("PRAGMA freelist_count").fetchone()[0]
            reclaim_detail = (pages - reusable) * self.page_size >= CLEAN_BYTES - RESERVE_BYTES
        with self.connection:
            # Reclaim before insertion can hit max_page_count. Allocated but reusable pages
            # are not pressure: SQLite files need not shrink after successful retention.
            if reclaim_detail:
                removed = self.connection.execute(
                    "DELETE FROM intervals WHERE (tier,boot,seq) IN (SELECT tier,boot,seq "
                    "FROM intervals WHERE tier=0 ORDER BY at LIMIT 100)"
                ).rowcount
                counts[0] = counts.get(0, 0) - removed
                early += removed
            inserted = self.connection.execute(
                "INSERT OR IGNORE INTO intervals VALUES (0,?,?,?,?,?)",
                (boot, seq, record["start"], until_at, packed),
            ).rowcount
            if not inserted:
                # A valid duplicate was already handled by the atomic boot watermark above.
                # Roll back any reclamation if the store has an inconsistent identity index.
                raise ValueError("missing_boot_watermark")
            self.connection.execute(
                "INSERT OR REPLACE INTO boots VALUES (?,?,?)",
                (boot, seq, max(until_at, previous_boot[1] if previous_boot else until_at)),
            )
            if boot_count > 10_000:
                oldest = self.connection.execute(
                    "SELECT boot,ended FROM boots WHERE boot!=? ORDER BY ended LIMIT 1", (boot,)
                ).fetchone()
                if oldest:
                    retired_boot_before = max(retired_boot_before, oldest[1])
                    self.connection.execute("DELETE FROM boots WHERE boot=?", (oldest[0],))
                    boot_count -= 1
            counts[0] = counts.get(0, 0) + 1
            old = self.connection.execute(
                "SELECT payload FROM intervals WHERE tier=1 AND boot='' AND seq=?", (hour,)
            ).fetchone()
            hourly = merge_hour(decode(old[0]), interval) if old else interval
            if old is None:
                counts[1] = counts.get(1, 0) + 1
            self.connection.execute(
                "INSERT OR REPLACE INTO intervals VALUES (1,'',?,?,?,?)",
                (hour, hourly["start"], hourly["end"], encode(hourly)),
            )
            self.connection.executemany(
                "INSERT INTO events VALUES (?,?,?,?,?)",
                [(boot, seq, index, until_at, body) for index, body in enumerate(packed_events)],
            )
            event_count += len(packed_events)
            for tier, rows, days in ((0, MINUTE_ROWS, 30), (1, HOUR_ROWS, 365)):
                expired = self.connection.execute(
                    "DELETE FROM intervals WHERE (tier,boot,seq) IN (SELECT tier,boot,seq "
                    "FROM intervals WHERE tier=? AND at<? ORDER BY at LIMIT 100)",
                    (tier, retention - days * 86400),
                ).rowcount
                counts[tier] -= expired
                excess = max(0, counts[tier] - rows)
                if excess:
                    removed = self.connection.execute(
                        "DELETE FROM intervals WHERE (tier,boot,seq) IN (SELECT tier,boot,seq "
                        "FROM intervals WHERE tier=? ORDER BY at LIMIT ?)",
                        (tier, min(100, excess)),
                    ).rowcount
                    counts[tier] -= removed
                    early += removed
            event_count -= self.connection.execute(
                "DELETE FROM events WHERE (boot,seq,item) IN (SELECT boot,seq,item "
                "FROM events WHERE at<? ORDER BY at LIMIT 100)",
                (retention - 90 * 86400,),
            ).rowcount
            if event_count > EVENT_ROWS:
                event_count -= self.connection.execute(
                    "DELETE FROM events WHERE (boot,seq,item) IN (SELECT boot,seq,item "
                    "FROM events ORDER BY at LIMIT ?)",
                    (min(100, event_count - EVENT_ROWS),),
                ).rowcount
            self.connection.executemany(
                "INSERT OR REPLACE INTO metadata VALUES (?,?)",
                [
                    ("retention_at", retention),
                    ("early_evictions", early),
                    ("retired_boot_before", retired_boot_before),
                ],
            )
        self.retention_at, self.early_evictions = retention, early
        self.counts, self.event_count = counts, event_count
        self.boot_count, self.retired_boot_before = boot_count, retired_boot_before
        self.writes += 1
        # The 128-page automatic checkpoint already bounds routine WAL growth. Avoid a second
        # checkpoint/fsync on every minute; FULL commit durability remains enabled.
        if self.writes % 60 == 0:
            self._checkpoint()
        self.last_write_seconds = time.monotonic() - started
        return True

    def status(self) -> dict[str, Any]:
        ranges = {}
        for tier, label in ((0, "minute"), (1, "hour")):
            first = self.connection.execute(
                "SELECT at FROM intervals WHERE tier=? ORDER BY at LIMIT 1", (tier,)
            ).fetchone()
            last = self.connection.execute(
                "SELECT until_at FROM intervals WHERE tier=? ORDER BY until_at DESC LIMIT 1",
                (tier,),
            ).fetchone()
            ranges[label] = {
                "rows": self.counts.get(tier, 0),
                "from": first[0] if first else None,
                "to": last[0] if last else None,
            }
        return {
            "state": "paused_storage" if self.paused else "recording",
            "error": None,
            "bytes": owned_bytes(self.directory),
            "ranges": ranges,
            "early_evictions": self.early_evictions,
            "write_seconds": getattr(self, "last_write_seconds", None),
        }

    def close(self) -> None:
        self.connection.close()


def read_page(
    directory: Path,
    *,
    tier: int,
    after: tuple[float, str, int] | None = None,
    limit: int = 100,
    before: float | None = None,
) -> list[dict[str, Any]]:
    path = directory / "history.sqlite3"
    if directory.is_symlink() or path.is_symlink() or not path.exists():
        return []
    owned_bytes(directory)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=0.02)
    try:
        deadline = time.monotonic() + 0.1
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
            raise ValueError("unsupported_schema")
        cursor = after or (-1.0, "", -1)
        rows = connection.execute(
            "SELECT at,boot,seq,substr(payload,1,?) FROM intervals "
            "WHERE tier=? AND (at,boot,seq)>(?,?,?) "
            "AND until_at<=? ORDER BY at,boot,seq LIMIT ?",
            (
                MAX_PAYLOAD + 1,
                tier,
                *cursor,
                before if before is not None else time.time(),
                max(1, min(100, limit)),
            ),
        ).fetchall()
        return [{"cursor": [row[0], row[1], row[2]], "record": decode(row[3])} for row in rows]
    finally:
        connection.close()


def read_events(
    directory: Path, *, after: tuple[float, str, int, int] | None = None, before: float
) -> list[dict[str, Any]]:
    path = directory / "history.sqlite3"
    if directory.is_symlink() or path.is_symlink() or not path.exists():
        return []
    owned_bytes(directory)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=0.02)
    try:
        deadline = time.monotonic() + 0.1
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
            raise ValueError("unsupported_schema")
        rows = connection.execute(
            "SELECT at,boot,seq,item,substr(payload,1,?) FROM events "
            "WHERE (at,boot,seq,item)>(?,?,?,?) "
            "AND at<=? ORDER BY at,boot,seq,item LIMIT 100",
            (MAX_EVENT_PAYLOAD + 1, *(after or (-1.0, "", -1, -1)), before),
        ).fetchall()
        return [{"cursor": list(row[:4]), "record": decode(row[4])} for row in rows]
    finally:
        connection.close()
