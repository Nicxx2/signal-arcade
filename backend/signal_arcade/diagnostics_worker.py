"""One bounded diagnostics I/O thread, isolated from the core's executor and database."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any

from .diagnostics_store import MAX_INPUT, DiagnosticsStore

WRITER_WAIT_REASONS = ("admission", "market_yield", "storage", "maintenance", "training", "guard")


def error_code(error: Exception) -> str:
    known = {
        "unsupported_schema",
        "record_too_large",
        "invalid_record",
        "invalid_message",
        "unexpected_diagnostic_files",
        "expired_boot_identity",
        "too_many_events",
        "invalid_identity",
        "invalid_time",
        "missing_boot_watermark",
    }
    if isinstance(error, ValueError) and str(error) in known:
        return str(error)
    if isinstance(error, sqlite3.Error):
        return str(getattr(error, "sqlite_errorname", "sqlite_error"))[:64]
    return type(error).__name__


class DiagnosticsWriter:
    def __init__(
        self,
        directory: Path,
        can_write: Callable[[], bool] | None = None,
        blocked_reason: Callable[[], str | None] | None = None,
    ) -> None:
        self.directory = directory
        self.can_write = can_write or (lambda: True)
        self.blocked_reason = blocked_reason
        self._wait_lock = threading.Lock()
        self._wait_reason: str | None = None
        self._wait_started = 0.0
        self._wait_counts = dict.fromkeys(WRITER_WAIT_REASONS, 0)
        self._wait_seconds = dict.fromkeys(WRITER_WAIT_REASONS, 0.0)
        self.messages: Queue[bytes | None] = Queue(maxsize=1)
        self.stopping = threading.Event()
        self.allowed = threading.Event()
        self.rejected = 0
        self.busy = False
        self.last_ack_monotonic: float | None = None
        self.status: dict[str, Any] = {"state": "starting"}
        self.thread = threading.Thread(target=self._run, name="diagnostics-io", daemon=True)

    def _observe_wait(self, reason: str | None) -> None:
        with self._wait_lock:
            if reason == self._wait_reason:
                return
            now = time.monotonic()
            if self._wait_reason is not None:
                prior = self._wait_reason
                self._wait_seconds[prior] = min(
                    1e12, self._wait_seconds[prior] + max(0.0, now - self._wait_started)
                )
            self._wait_reason, self._wait_started = reason, now
            if reason is not None:
                self._wait_counts[reason] = min(2**53 - 1, self._wait_counts[reason] + 1)

    def wait_status(self) -> dict[str, Any]:
        """Sampled writer waits, separate from collector admission and SQLite write time."""
        with self._wait_lock:
            age = max(0.0, time.monotonic() - self._wait_started) if self._wait_reason else 0.0
            seconds = dict(self._wait_seconds)
            if self._wait_reason is not None:
                seconds[self._wait_reason] = min(1e12, seconds[self._wait_reason] + age)
            return {
                "reason": self._wait_reason,
                "reason_age_seconds": round(min(1e12, age), 6),
                "episodes_since_boot": dict(self._wait_counts),
                "seconds_since_boot": {key: round(value, 6) for key, value in seconds.items()},
            }

    def _record_blocked_wait(self, admission: bool) -> None:
        # These observations cannot grant write permission or break the writer. A reason
        # sampled after a guard denial may already have changed; retain "guard" honestly.
        reason = "admission" if not admission else "guard"
        with suppress(Exception):
            if admission and self.blocked_reason is not None:
                observed = self.blocked_reason()
                if isinstance(observed, str) and observed in WRITER_WAIT_REASONS:
                    reason = observed
        with suppress(Exception):
            self._observe_wait(reason)

    def offer(self, raw: bytes) -> bool:
        if len(raw) > MAX_INPUT or not self.thread.is_alive():
            return False
        try:
            self.messages.put_nowait(raw)
            return True
        except Full:
            return False

    def _run(self) -> None:
        started_cpu = time.thread_time()
        try:
            if self.directory.is_symlink():
                raise ValueError("unexpected_diagnostic_files")
            self.directory.mkdir(parents=True, exist_ok=True)
            lock_path = self.directory / "writer.lock"
            if lock_path.is_symlink():
                raise ValueError("unexpected_diagnostic_files")
            with lock_path.open("a+b") as ownership:
                if os.name == "posix":
                    import fcntl

                    fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    import msvcrt

                    ownership.seek(0)
                    if not ownership.read(1):
                        ownership.write(b"0")
                        ownership.flush()
                    ownership.seek(0)
                    # Windows-only API is absent from the Linux typing stub.
                    msvcrt.locking(ownership.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                store = DiagnosticsStore(self.directory)
                try:
                    self.status = {**store.status(), "last_ack_at": time.time()}
                    self.last_ack_monotonic = time.monotonic()
                    while not self.stopping.is_set():
                        raw = self.messages.get()
                        if raw is None:
                            break
                        self.busy = True
                        while not self.stopping.is_set():
                            admission = self.allowed.is_set()
                            if admission and self.can_write():
                                with suppress(Exception):
                                    self._observe_wait(None)
                                break
                            self._record_blocked_wait(admission)
                            self.stopping.wait(0.1)
                        if self.stopping.is_set():
                            break
                        try:
                            record = json.loads(raw)
                            rss = None
                            if os.name == "posix":
                                with suppress(OSError, ValueError, IndexError):
                                    pages = int(Path("/proc/self/statm").read_text().split()[1])
                                    rss = pages * os.sysconf("SC_PAGE_SIZE")
                            record["gauges"]["app_rss_bytes"] = rss
                            accepted = store.append(record)
                            self.rejected += int(not accepted)
                            self.status = {
                                **store.status(),
                                "last_ack_at": time.time(),
                                "writer_cpu_seconds": time.thread_time() - started_cpu,
                            }
                        except Exception as error:
                            self.rejected += 1
                            self.status = {
                                **self.status,
                                "state": "paused_error",
                                "error": error_code(error),
                                "last_ack_at": time.time(),
                            }
                        finally:
                            self.last_ack_monotonic = time.monotonic()
                            self.busy = False
                finally:
                    store.close()
        except Exception as error:
            self.status = {**self.status, "state": "unavailable", "error": error_code(error)}
        finally:
            with suppress(Exception):
                self._observe_wait(None)

    def request_stop(self) -> None:
        self.stopping.set()
        # A sentinel wakes an idle writer. A queued record is expendable diagnostic detail.
        with suppress(Empty):
            self.messages.get_nowait()
        with suppress(Full):
            self.messages.put_nowait(None)
