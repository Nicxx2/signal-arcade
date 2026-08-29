from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    AiCriticAssessment,
    CoachHypothesis,
    CoachReview,
    Decision,
    FillReceipt,
    LearningModel,
    LearningObservation,
    MarketEvent,
    OperationalIncident,
    PaperOrder,
    Position,
)

SCHEMA_VERSION = 7


class Database:
    """Small SQLite store with WAL, foreign keys, migrations, and immutable journals."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._reader_lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._storage_cache: dict[str, int] | None = None
        self._storage_cache_at = 0.0
        self._storage_revision = 0
        self._migrate()
        # WAL permits a reader to retain the last committed view while the maintenance writer
        # retires old rows.  Keeping UI/decision reads off the writer's in-process RLock prevents
        # a bounded cleanup pass from becoming an application-wide pause.
        self._reader_conn = sqlite3.connect(path, check_same_thread=False, timeout=1)
        self._reader_conn.row_factory = sqlite3.Row
        self._reader_conn.execute("PRAGMA query_only=ON")
        self._reader_conn.execute("PRAGMA busy_timeout=250")

    def close(self) -> None:
        with self._reader_lock:
            self._reader_conn.close()
        with self._lock:
            self._conn.close()

    def _migrate(self) -> None:
        with self._lock, self._conn:
            version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema {version} is newer than supported {SCHEMA_VERSION}"
                )
            if version == 0:
                self._conn.executescript(
                    """
                    CREATE TABLE settings (
                        key TEXT PRIMARY KEY,
                        value_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE market_events (
                        event_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        mint TEXT,
                        signature TEXT,
                        slot INTEGER,
                        block_time TEXT,
                        received_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_market_events_mint_time
                        ON market_events(mint, received_at DESC);
                    CREATE INDEX idx_market_events_received_at
                        ON market_events(received_at DESC);
                    CREATE INDEX idx_market_events_kind_time
                        ON market_events(kind, received_at);
                    CREATE TABLE decisions (
                        decision_id TEXT PRIMARY KEY,
                        mint TEXT NOT NULL,
                        action TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_decisions_created ON decisions(created_at DESC);
                    CREATE TABLE paper_orders (
                        order_id TEXT PRIMARY KEY,
                        mint TEXT NOT NULL,
                        side TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_orders_status ON paper_orders(status, created_at);
                    CREATE TABLE fills (
                        fill_id TEXT PRIMARY KEY,
                        order_id TEXT NOT NULL UNIQUE,
                        mint TEXT NOT NULL,
                        side TEXT NOT NULL,
                        filled_at TEXT NOT NULL,
                        record_json TEXT NOT NULL,
                        FOREIGN KEY(order_id) REFERENCES paper_orders(order_id)
                    );
                    CREATE TABLE positions (
                        position_id TEXT PRIMARY KEY,
                        mint TEXT NOT NULL UNIQUE,
                        opened_at TEXT NOT NULL,
                        record_json TEXT NOT NULL
                    );
                    CREATE TABLE ledger_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tx_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        account TEXT NOT NULL,
                        debit_lamports INTEGER NOT NULL DEFAULT 0 CHECK(debit_lamports >= 0),
                        credit_lamports INTEGER NOT NULL DEFAULT 0 CHECK(credit_lamports >= 0),
                        memo TEXT NOT NULL
                    );
                    CREATE INDEX idx_ledger_tx ON ledger_entries(tx_id);
                    CREATE TABLE provider_usage (
                        provider TEXT NOT NULL,
                        month TEXT NOT NULL,
                        calls INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(provider, month)
                    );
                    CREATE TABLE equity_points (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        recorded_at TEXT NOT NULL,
                        equity_lamports INTEGER NOT NULL,
                        cash_lamports INTEGER NOT NULL
                    );
                    CREATE TABLE learning_observations (
                        observation_id TEXT PRIMARY KEY,
                        mint TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_learning_observations_status
                        ON learning_observations(status, created_at);
                    CREATE TABLE learning_models (
                        version TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        qualified INTEGER NOT NULL,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_learning_models_created
                        ON learning_models(created_at);
                    CREATE TABLE ai_critic_assessments (
                        assessment_id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        valid INTEGER NOT NULL,
                        resolved_at TEXT,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_ai_assessments_decision
                        ON ai_critic_assessments(decision_id, created_at);
                    CREATE INDEX idx_ai_assessments_resolved
                        ON ai_critic_assessments(resolved_at, created_at);
                    CREATE TABLE coach_reviews (
                        review_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        risk_mode TEXT NOT NULL,
                        configuration_fingerprint TEXT NOT NULL,
                        valid INTEGER NOT NULL,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_coach_reviews_created
                        ON coach_reviews(created_at DESC);
                    CREATE TABLE coach_hypotheses (
                        hypothesis_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        state TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        risk_mode TEXT NOT NULL,
                        configuration_fingerprint TEXT NOT NULL,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_coach_hypotheses_context
                        ON coach_hypotheses(risk_mode, configuration_fingerprint, created_at DESC);
                    CREATE TABLE operational_incidents (
                        incident_id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        occurrences INTEGER NOT NULL,
                        resolved_at TEXT,
                        record_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_incidents_active
                        ON operational_incidents(scope, resolved_at, last_seen_at DESC);
                    CREATE TABLE equity_rollups (
                        bucket_start TEXT PRIMARY KEY,
                        open_equity_lamports INTEGER NOT NULL,
                        high_equity_lamports INTEGER NOT NULL,
                        low_equity_lamports INTEGER NOT NULL,
                        close_equity_lamports INTEGER NOT NULL,
                        close_cash_lamports INTEGER NOT NULL,
                        samples INTEGER NOT NULL
                    );
                    CREATE TABLE paper_seasons (
                        season_id TEXT PRIMARY KEY,
                        season_number INTEGER NOT NULL UNIQUE,
                        started_at TEXT NOT NULL,
                        ended_at TEXT,
                        quote_currency TEXT NOT NULL,
                        quote_decimals INTEGER NOT NULL,
                        starting_minor INTEGER NOT NULL CHECK(starting_minor >= 0),
                        ending_equity_minor INTEGER,
                        last_known_ending_equity_minor INTEGER,
                        peak_equity_minor INTEGER NOT NULL DEFAULT 0,
                        realized_pnl_minor INTEGER NOT NULL DEFAULT 0,
                        net_pnl_minor INTEGER NOT NULL DEFAULT 0,
                        total_fees_minor INTEGER NOT NULL DEFAULT 0,
                        closed_trades INTEGER NOT NULL DEFAULT 0,
                        wins INTEGER NOT NULL DEFAULT 0,
                        losses INTEGER NOT NULL DEFAULT 0,
                        break_even INTEGER NOT NULL DEFAULT 0,
                        ending_drawdown_fraction REAL NOT NULL DEFAULT 0,
                        open_positions INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL CHECK(status IN ('current','completed'))
                    );
                    CREATE INDEX idx_paper_seasons_number
                        ON paper_seasons(season_number DESC);
                    CREATE UNIQUE INDEX idx_paper_seasons_one_current
                        ON paper_seasons(status) WHERE status='current';
                    """
                )
                self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            else:
                if version == 1:
                    self._conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_market_events_kind_time "
                        "ON market_events(kind, received_at)"
                    )
                    version = 2
                if version < 3:
                    self._conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS learning_observations (
                            observation_id TEXT PRIMARY KEY,
                            mint TEXT NOT NULL UNIQUE,
                            created_at TEXT NOT NULL,
                            status TEXT NOT NULL,
                            record_json TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_learning_observations_status
                            ON learning_observations(status, created_at);
                        CREATE TABLE IF NOT EXISTS learning_models (
                            version TEXT PRIMARY KEY,
                            created_at TEXT NOT NULL,
                            qualified INTEGER NOT NULL,
                            record_json TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_learning_models_created
                            ON learning_models(created_at);
                        """
                    )
                    version = 3
                if version < 4:
                    # recent_events() is used during every startup. Without this global time
                    # index SQLite sorts full payload rows into temporary storage before LIMIT,
                    # which can exhaust a small container tmpfs even when the disk is healthy.
                    self._conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_market_events_received_at "
                        "ON market_events(received_at DESC)"
                    )
                    version = 4
                if version < 5:
                    self._conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS ai_critic_assessments (
                            assessment_id TEXT PRIMARY KEY,
                            decision_id TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            valid INTEGER NOT NULL,
                            resolved_at TEXT,
                            record_json TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_ai_assessments_decision
                            ON ai_critic_assessments(decision_id, created_at);
                        CREATE INDEX IF NOT EXISTS idx_ai_assessments_resolved
                            ON ai_critic_assessments(resolved_at, created_at);
                        CREATE TABLE IF NOT EXISTS operational_incidents (
                            incident_id TEXT PRIMARY KEY,
                            scope TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            title TEXT NOT NULL,
                            first_seen_at TEXT NOT NULL,
                            last_seen_at TEXT NOT NULL,
                            occurrences INTEGER NOT NULL,
                            resolved_at TEXT,
                            record_json TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_incidents_active
                            ON operational_incidents(scope, resolved_at, last_seen_at DESC);
                        CREATE TABLE IF NOT EXISTS equity_rollups (
                            bucket_start TEXT PRIMARY KEY,
                            open_equity_lamports INTEGER NOT NULL,
                            high_equity_lamports INTEGER NOT NULL,
                            low_equity_lamports INTEGER NOT NULL,
                            close_equity_lamports INTEGER NOT NULL,
                            close_cash_lamports INTEGER NOT NULL,
                            samples INTEGER NOT NULL
                        );
                        INSERT OR IGNORE INTO equity_rollups
                        WITH ranked AS (
                            SELECT
                                strftime('%Y-%m-%dT%H:00:00+00:00', recorded_at)
                                    AS bucket_start,
                                equity_lamports,
                                cash_lamports,
                                ROW_NUMBER() OVER (
                                    PARTITION BY strftime(
                                        '%Y-%m-%dT%H:00:00+00:00', recorded_at
                                    ) ORDER BY id
                                ) AS first_in_bucket,
                                ROW_NUMBER() OVER (
                                    PARTITION BY strftime(
                                        '%Y-%m-%dT%H:00:00+00:00', recorded_at
                                    ) ORDER BY id DESC
                                ) AS last_in_bucket
                            FROM equity_points
                        )
                        SELECT
                            bucket_start,
                            MAX(CASE WHEN first_in_bucket=1 THEN equity_lamports END),
                            MAX(equity_lamports),
                            MIN(equity_lamports),
                            MAX(CASE WHEN last_in_bucket=1 THEN equity_lamports END),
                            MAX(CASE WHEN last_in_bucket=1 THEN cash_lamports END),
                            COUNT(*)
                        FROM ranked
                        WHERE bucket_start IS NOT NULL
                        GROUP BY bucket_start;
                        """
                    )
                    version = 5
                if version < 6:
                    self._conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS paper_seasons (
                            season_id TEXT PRIMARY KEY,
                            season_number INTEGER NOT NULL UNIQUE,
                            started_at TEXT NOT NULL,
                            ended_at TEXT,
                            quote_currency TEXT NOT NULL,
                            quote_decimals INTEGER NOT NULL,
                            starting_minor INTEGER NOT NULL CHECK(starting_minor >= 0),
                            ending_equity_minor INTEGER,
                            last_known_ending_equity_minor INTEGER,
                            peak_equity_minor INTEGER NOT NULL DEFAULT 0,
                            realized_pnl_minor INTEGER NOT NULL DEFAULT 0,
                            net_pnl_minor INTEGER NOT NULL DEFAULT 0,
                            total_fees_minor INTEGER NOT NULL DEFAULT 0,
                            closed_trades INTEGER NOT NULL DEFAULT 0,
                            wins INTEGER NOT NULL DEFAULT 0,
                            losses INTEGER NOT NULL DEFAULT 0,
                            break_even INTEGER NOT NULL DEFAULT 0,
                            ending_drawdown_fraction REAL NOT NULL DEFAULT 0,
                            open_positions INTEGER NOT NULL DEFAULT 0,
                            status TEXT NOT NULL CHECK(status IN ('current','completed'))
                        );
                        CREATE INDEX IF NOT EXISTS idx_paper_seasons_number
                            ON paper_seasons(season_number DESC);
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_seasons_one_current
                            ON paper_seasons(status) WHERE status='current';
                        """
                    )
                    version = 6
                if version < 7:
                    self._conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS coach_reviews (
                            review_id TEXT PRIMARY KEY,
                            created_at TEXT NOT NULL,
                            risk_mode TEXT NOT NULL,
                            configuration_fingerprint TEXT NOT NULL,
                            valid INTEGER NOT NULL,
                            record_json TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_coach_reviews_created
                            ON coach_reviews(created_at DESC);
                        CREATE TABLE IF NOT EXISTS coach_hypotheses (
                            hypothesis_id TEXT PRIMARY KEY,
                            created_at TEXT NOT NULL,
                            state TEXT NOT NULL,
                            kind TEXT NOT NULL,
                            risk_mode TEXT NOT NULL,
                            configuration_fingerprint TEXT NOT NULL,
                            record_json TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_coach_hypotheses_context
                            ON coach_hypotheses(
                                risk_mode, configuration_fingerprint, created_at DESC
                            );
                        """
                    )
                    version = 7
                self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def health_check(self) -> bool:
        """Cheap, non-blocking liveness probe.

        Storage maintenance and dashboard reads can legitimately own either connection lock for a
        short period. Waiting for one would make Docker treat healthy work as a dead process. A
        busy in-process reader therefore means "alive and working"; otherwise the low-timeout WAL
        reader verifies SQLite without joining the maintenance writer's five-second busy wait.
        """
        acquired = self._reader_lock.acquire(blocking=False)
        if not acquired:
            return True
        try:
            result = self._reader_conn.execute("SELECT 1").fetchone()[0]
        except sqlite3.Error:
            return False
        finally:
            self._reader_lock.release()
        return bool(result == 1)

    def integrity_check(self) -> bool:
        """Explicit, potentially expensive database verification for maintenance/tests."""
        with self._lock:
            result = self._conn.execute("PRAGMA quick_check").fetchone()[0]
        return bool(result == "ok")

    def prune_history(
        self,
        raw_trade_before: datetime,
        *,
        non_entry_decision_before: datetime | None = None,
        max_equity_points: int = 20_000,
        max_rows_per_category: int = 1_000,
    ) -> dict[str, int]:
        """Bound high-volume samples while retaining fills, orders, and entry evidence.

        Each maintenance pass removes a bounded number of large raw rows.  This prevents an old,
        multi-gigabyte history from monopolising the shared SQLite connection at startup.
        """
        if max_rows_per_category < 1:
            raise ValueError("max rows per category must be positive")
        with self._lock, self._conn:
            trades = self._conn.execute(
                """DELETE FROM market_events WHERE event_id IN (
                       SELECT event_id FROM market_events
                       WHERE kind=? AND received_at<?
                       ORDER BY received_at ASC LIMIT ?
                   )""",
                ("trade", raw_trade_before.isoformat(), max_rows_per_category),
            ).rowcount
            decisions = 0
            if non_entry_decision_before is not None:
                decisions = self._conn.execute(
                    """DELETE FROM decisions WHERE decision_id IN (
                           SELECT decision_id FROM decisions
                           WHERE action!='enter' AND created_at<?
                           ORDER BY created_at ASC LIMIT ?
                       )""",
                    (non_entry_decision_before.isoformat(), max_rows_per_category),
                ).rowcount
            equity = self._conn.execute(
                """DELETE FROM equity_points WHERE id NOT IN (
                       SELECT id FROM equity_points ORDER BY id DESC LIMIT ?
                   )""",
                (max_equity_points,),
            ).rowcount
        self._invalidate_storage_cache()
        return {
            "raw_trades": max(0, trades),
            "non_entry_decisions": max(0, decisions),
            "equity_points": max(0, equity),
        }

    def enforce_storage_budget(
        self,
        max_database_bytes: int,
        *,
        preserve_recent_events: int = 20_000,
        preserve_recent_non_entry_decisions: int = 5_000,
        max_rows_per_pass: int = 250_000,
        stop_requested: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        """Free reusable SQLite pages before the configured live-data budget is crossed.

        SQLite deliberately keeps freed pages inside the database file for fast reuse, so an
        existing file may remain larger than a newly selected limit. ``live_bytes`` is the
        meaningful growth measure; immutable fills, orders, ledger entries, positions, learning
        records, and every ENTER decision are never removed here.
        """
        if max_database_bytes < 1:
            raise ValueError("max database bytes must be positive")
        if max_rows_per_pass < 1:
            raise ValueError("max rows per pass must be positive")
        target = int(max_database_bytes * 0.90)
        removed_events = 0
        removed_decisions = 0
        # Keep individual write locks short while allowing one five-minute pass to retire a
        # genuinely busy legacy backlog. New untracked candidate ticks are no longer durable.
        chunk_size = 5_000
        with self._lock:
            event_count = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM market_events WHERE kind='trade'"
                ).fetchone()[0]
            )
            decision_count = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM decisions WHERE action!='enter'"
                ).fetchone()[0]
            )
        removable_events = max(0, event_count - preserve_recent_events)
        removable_decisions = max(0, decision_count - preserve_recent_non_entry_decisions)
        chunks = 0

        while removed_events + removed_decisions < max_rows_per_pass:
            # Upgrade preparation may arrive while a large legacy backlog is being retired.
            # Every chunk is its own committed transaction, so stopping between chunks is safe
            # and prevents routine cleanup from delaying a container update for minutes.
            if stop_requested is not None and stop_requested():
                break
            if chunks % 5 == 0 and self._page_usage()["live_bytes"] <= target:
                break
            remaining = max_rows_per_pass - removed_events - removed_decisions
            with self._lock, self._conn:
                if removable_events > 0:
                    deleted = self._conn.execute(
                        """DELETE FROM market_events WHERE event_id IN (
                               SELECT event_id FROM market_events WHERE kind='trade'
                               ORDER BY received_at ASC LIMIT ?
                           )""",
                        (min(chunk_size, removable_events, remaining),),
                    ).rowcount
                    removed = max(0, deleted)
                    removed_events += removed
                    removable_events -= removed
                elif removable_decisions > 0:
                    deleted = self._conn.execute(
                        """DELETE FROM decisions WHERE decision_id IN (
                               SELECT decision_id FROM decisions WHERE action!='enter'
                               ORDER BY created_at ASC LIMIT ?
                           )""",
                        (min(chunk_size, removable_decisions, remaining),),
                    ).rowcount
                    removed = max(0, deleted)
                    removed_decisions += removed
                    removable_decisions -= removed
                else:
                    break
            chunks += 1
            # Give waiting event/heartbeat workers a fair chance to take the connection between
            # chunks; RLock acquisition is not guaranteed to be fair across threads.
            time.sleep(0.01)

        self._invalidate_storage_cache()
        usage = self._page_usage()
        return {
            "raw_trades": removed_events,
            "non_entry_decisions": removed_decisions,
            "live_bytes": usage["live_bytes"],
            "reclaimable_bytes": usage["reclaimable_bytes"],
        }

    def _page_usage(self) -> dict[str, int]:
        with self._lock:
            page_size = int(self._conn.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(self._conn.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(self._conn.execute("PRAGMA freelist_count").fetchone()[0])
        allocated = page_size * page_count
        reclaimable = page_size * free_pages
        return {
            "database_bytes": allocated,
            "live_bytes": max(0, allocated - reclaimable),
            "reclaimable_bytes": reclaimable,
        }

    def storage_stats(self, *, force: bool = False) -> dict[str, int]:
        now = time.monotonic()
        with self._lock:
            if not force and self._storage_cache is not None and now - self._storage_cache_at < 60:
                return dict(self._storage_cache)
            revision = self._storage_revision
        count_queries = {
            "market_events": "SELECT COUNT(*) FROM market_events",
            "decisions": "SELECT COUNT(*) FROM decisions",
            "paper_orders": "SELECT COUNT(*) FROM paper_orders",
            "fills": "SELECT COUNT(*) FROM fills",
            "positions": "SELECT COUNT(*) FROM positions",
            "equity_points": "SELECT COUNT(*) FROM equity_points",
            "equity_rollups": "SELECT COUNT(*) FROM equity_rollups",
            "paper_seasons": "SELECT COUNT(*) FROM paper_seasons",
            "learning_observations": "SELECT COUNT(*) FROM learning_observations",
            "learning_models": "SELECT COUNT(*) FROM learning_models",
            "ai_critic_assessments": "SELECT COUNT(*) FROM ai_critic_assessments",
            "coach_reviews": "SELECT COUNT(*) FROM coach_reviews",
            "coach_hypotheses": "SELECT COUNT(*) FROM coach_hypotheses",
            "operational_incidents": "SELECT COUNT(*) FROM operational_incidents",
        }
        with self._lock:
            rows = {
                table: int(self._conn.execute(query).fetchone()[0])
                for table, query in count_queries.items()
            }
        rows.update(self._page_usage())
        wal_path = Path(str(self.path) + "-wal")
        rows["wal_bytes"] = wal_path.stat().st_size if wal_path.exists() else 0
        rows["total_disk_bytes"] = rows["database_bytes"] + rows["wal_bytes"]
        with self._lock:
            # A writer may have committed after the counts were read. Return this point-in-time
            # view, but never cache it over that writer's invalidation for the next dashboard read.
            if revision == self._storage_revision:
                self._storage_cache = dict(rows)
                self._storage_cache_at = now
        return rows

    def _invalidate_storage_cache(self) -> None:
        with self._lock:
            self._storage_revision += 1
            self._storage_cache = None

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._reader_lock:
            row = self._reader_conn.execute(
                "SELECT value_json FROM settings WHERE key=?", (key,)
            ).fetchone()
        return default if row is None else json.loads(row["value_json"])

    def set_setting(self, key: str, value: Any) -> None:
        self.set_settings({key: value})

    def set_settings(self, values: dict[str, Any]) -> None:
        """Persist a related configuration update in one short transaction."""

        if not values:
            return
        now = datetime.now().astimezone().isoformat()
        with self._lock, self._conn:
            self._upsert_settings(values.items(), now)

    def initialize_portfolio(self, tx_id: str, starting_minor: int, quote_currency: str) -> None:
        """Atomically create the first virtual bankroll and all of its durable settings."""
        if starting_minor <= 0:
            raise ValueError("starting bankroll must be positive")
        now = datetime.now().astimezone().isoformat()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT value_json FROM settings WHERE key='portfolio_initialized'"
            ).fetchone()
            if row is not None and bool(json.loads(row[0])):
                raise ValueError("paper portfolio is already initialized")
            ledger_count = int(
                self._conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]
            )
            if ledger_count:
                raise RuntimeError("uninitialized portfolio contains unexpected ledger entries")
            self._insert_ledger(
                tx_id,
                now,
                [
                    ("cash", starting_minor, 0, "Initial virtual bankroll"),
                    ("capital", 0, starting_minor, "Initial virtual bankroll"),
                ],
            )
            self._upsert_settings(
                [
                    ("portfolio_initialized", True),
                    ("quote_currency", quote_currency),
                    ("starting_lamports", starting_minor),
                    ("realized_pnl_lamports", 0),
                    ("peak_equity_lamports", starting_minor),
                    ("equity_peak_basis", "executable-route-v1"),
                    ("season_id", tx_id),
                ],
                now,
            )
            self._insert_current_season(
                season_id=tx_id,
                started_at=now,
                quote_currency=quote_currency,
                starting_minor=starting_minor,
            )
            self._conn.execute(
                """INSERT INTO equity_points(
                    recorded_at,equity_lamports,cash_lamports) VALUES(?,?,?)""",
                (now, starting_minor, starting_minor),
            )

    def _insert_current_season(
        self,
        *,
        season_id: str,
        started_at: str,
        quote_currency: str,
        starting_minor: int,
    ) -> None:
        """Insert the one active paper season inside the caller's transaction."""

        active = self._conn.execute(
            "SELECT season_id FROM paper_seasons WHERE status='current'"
        ).fetchone()
        if active is not None:
            if str(active[0]) == season_id:
                return
            raise RuntimeError("another paper season is already active")
        number = int(
            self._conn.execute(
                "SELECT COALESCE(MAX(season_number),0)+1 FROM paper_seasons"
            ).fetchone()[0]
        )
        decimals = 9 if quote_currency == "SOL" else 6
        self._conn.execute(
            """INSERT INTO paper_seasons(
                   season_id,season_number,started_at,quote_currency,quote_decimals,
                   starting_minor,peak_equity_minor,status
               ) VALUES(?,?,?,?,?,?,?,'current')""",
            (
                season_id,
                number,
                started_at,
                quote_currency,
                decimals,
                starting_minor,
                starting_minor,
            ),
        )

    def ensure_current_season(
        self,
        season_id: str,
        starting_minor: int,
        quote_currency: str,
    ) -> None:
        """Backfill the durable summary row for a season created before schema v6."""

        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT 1 FROM paper_seasons WHERE season_id=?", (season_id,)
            ).fetchone()
            if existing is not None:
                return
            started_at = self._conn.execute(
                """SELECT MIN(value) FROM (
                       SELECT MIN(recorded_at) AS value FROM equity_points
                       UNION ALL SELECT MIN(filled_at) FROM fills
                       UNION ALL SELECT MIN(created_at) FROM paper_orders
                       UNION ALL SELECT MIN(created_at) FROM decisions
                       UNION ALL SELECT MIN(created_at) FROM ledger_entries
                   ) WHERE value IS NOT NULL"""
            ).fetchone()[0]
            self._insert_current_season(
                season_id=season_id,
                started_at=str(started_at or datetime.now().astimezone().isoformat()),
                quote_currency=quote_currency,
                starting_minor=starting_minor,
            )

    def list_paper_seasons(self) -> list[dict[str, Any]]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT * FROM paper_seasons ORDER BY season_number"
            ).fetchall()
        return [dict(row) for row in rows]

    def _upsert_settings(self, items: Iterable[tuple[str, Any]], now: str) -> None:
        self._conn.executemany(
            """INSERT INTO settings(key, value_json, updated_at) VALUES(?,?,?)
               ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
               updated_at=excluded.updated_at""",
            [(key, json.dumps(value, separators=(",", ":")), now) for key, value in items],
        )

    def append_event(self, event: MarketEvent) -> bool:
        return event.event_id in self.append_events([event])

    def append_events(self, events: Sequence[MarketEvent]) -> set[str]:
        """Persist a network batch in one transaction and return newly inserted IDs."""

        inserted: set[str] = set()
        with self._lock, self._conn:
            for event in events:
                cursor = self._conn.execute(
                    """INSERT OR IGNORE INTO market_events(
                        event_id,source,kind,mint,signature,slot,block_time,received_at,
                        schema_version,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event.event_id,
                        event.source,
                        event.kind.value,
                        event.mint,
                        event.signature,
                        event.slot,
                        event.block_time.isoformat() if event.block_time else None,
                        event.received_at.isoformat(),
                        event.schema_version,
                        json.dumps(event.payload, separators=(",", ":")),
                    ),
                )
                if cursor.rowcount == 1:
                    inserted.add(event.event_id)
        if inserted:
            self._invalidate_storage_cache()
        return inserted

    def recent_events(self, limit: int = 10_000) -> list[MarketEvent]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT * FROM market_events ORDER BY received_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._event_from_row(row) for row in reversed(rows)]

    def events_for_mints(
        self,
        mints: Iterable[str],
        *,
        kinds: Sequence[str] | None = None,
    ) -> list[MarketEvent]:
        mint_values = sorted(set(mints))
        if not mint_values:
            return []
        mint_marks = ",".join("?" for _ in mint_values)
        conditions = [f"mint IN ({mint_marks})"]  # noqa: S608 - placeholders only
        parameters: list[str] = list(mint_values)
        if kinds:
            kind_marks = ",".join("?" for _ in kinds)
            conditions.append(f"kind IN ({kind_marks})")
            parameters.extend(kinds)
        query = "SELECT * FROM market_events WHERE " + " AND ".join(conditions)  # noqa: S608
        query += " ORDER BY received_at"
        with self._reader_lock:
            rows = self._reader_conn.execute(query, parameters).fetchall()
        return [self._event_from_row(row) for row in rows]

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> MarketEvent:
        return MarketEvent(
            event_id=row["event_id"],
            source=row["source"],
            kind=row["kind"],
            mint=row["mint"],
            signature=row["signature"],
            slot=row["slot"],
            block_time=row["block_time"],
            received_at=row["received_at"],
            schema_version=row["schema_version"],
            payload=json.loads(row["payload_json"]),
        )

    def save_decision(self, decision: Decision) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO decisions VALUES(?,?,?,?,?)",
                (
                    decision.decision_id,
                    decision.mint,
                    decision.action.value,
                    decision.created_at.isoformat(),
                    decision.model_dump_json(),
                ),
            )

    def list_decisions(self, limit: int = 100) -> list[Decision]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Decision.model_validate_json(row[0]) for row in rows]

    def list_decisions_by_actions(
        self,
        actions: Sequence[str],
        limit: int = 100,
    ) -> list[Decision]:
        """Return a bounded action lane without scanning a burst-sized dashboard payload."""

        selected = tuple(dict.fromkeys(actions))
        if not selected or limit < 1:
            return []
        placeholders = ",".join("?" for _ in selected)
        with self._reader_lock:
            rows = self._reader_conn.execute(
                f"""SELECT record_json FROM decisions
                    WHERE action IN ({placeholders})
                    ORDER BY created_at DESC LIMIT ?""",  # noqa: S608 - placeholders only
                (*selected, limit),
            ).fetchall()
        return [Decision.model_validate_json(row[0]) for row in rows]

    def get_decision(self, decision_id: str) -> Decision | None:
        with self._reader_lock:
            row = self._reader_conn.execute(
                "SELECT record_json FROM decisions WHERE decision_id=?", (decision_id,)
            ).fetchone()
        return None if row is None else Decision.model_validate_json(row[0])

    def save_learning_observation(self, observation: LearningObservation) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO learning_observations VALUES(?,?,?,?,?)
                   ON CONFLICT(observation_id) DO UPDATE SET
                   status=excluded.status,record_json=excluded.record_json""",
                (
                    observation.observation_id,
                    observation.mint,
                    observation.created_at.isoformat(),
                    observation.status.value,
                    observation.model_dump_json(),
                ),
            )

    def list_learning_observations(self) -> list[LearningObservation]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM learning_observations ORDER BY created_at"
            ).fetchall()
        return [LearningObservation.model_validate_json(row[0]) for row in rows]

    def learning_observation_for_decision(self, decision_id: str) -> LearningObservation | None:
        with self._reader_lock:
            row = self._reader_conn.execute(
                "SELECT record_json FROM learning_observations "
                "WHERE json_extract(record_json,'$.decision_id')=? LIMIT 1",
                (decision_id,),
            ).fetchone()
        return None if row is None else LearningObservation.model_validate_json(row[0])

    def prune_learning_observations(self, max_complete: int) -> list[str]:
        """Keep pending lessons and only the newest bounded set of completed lessons."""
        if max_complete < 0:
            raise ValueError("max_complete must not be negative")
        with self._lock, self._conn:
            rows = self._conn.execute(
                """SELECT observation_id,mint FROM learning_observations
                   WHERE status=? ORDER BY created_at DESC LIMIT -1 OFFSET ?""",
                ("complete", max_complete),
            ).fetchall()
            self._conn.executemany(
                "DELETE FROM learning_observations WHERE observation_id=?",
                ((str(row[0]),) for row in rows),
            )
        return [str(row[1]) for row in rows]

    def save_learning_model(self, model: LearningModel) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO learning_models VALUES(?,?,?,?)",
                (
                    model.version,
                    model.created_at.isoformat(),
                    int(model.qualified),
                    model.model_dump_json(),
                ),
            )

    def list_learning_models(self) -> list[LearningModel]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM learning_models ORDER BY created_at"
            ).fetchall()
        return [LearningModel.model_validate_json(row[0]) for row in rows]

    def prune_learning_models(
        self,
        max_models: int,
        *,
        preserve_versions: set[str] | None = None,
    ) -> list[str]:
        """Bound challenger artifacts while retaining active/safety-audit versions."""

        if max_models < 1:
            raise ValueError("max_models must be positive")
        protected = set(preserve_versions or set())
        with self._lock, self._conn:
            versions = [
                str(row[0])
                for row in self._conn.execute(
                    "SELECT version FROM learning_models ORDER BY created_at DESC"
                ).fetchall()
            ]
            keep = {version for version in versions if version in protected}
            for version in versions:
                if len(keep) >= max_models:
                    break
                keep.add(version)
            removed = [version for version in versions if version not in keep]
            self._conn.executemany(
                "DELETE FROM learning_models WHERE version=?",
                ((version,) for version in removed),
            )
        self._invalidate_storage_cache()
        return removed

    def save_ai_assessment(self, assessment: AiCriticAssessment) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO ai_critic_assessments VALUES(?,?,?,?,?,?)
                   ON CONFLICT(assessment_id) DO UPDATE SET
                   valid=excluded.valid,resolved_at=excluded.resolved_at,
                   record_json=excluded.record_json""",
                (
                    assessment.assessment_id,
                    assessment.decision_id,
                    assessment.created_at.isoformat(),
                    int(assessment.valid),
                    assessment.resolved_at.isoformat() if assessment.resolved_at else None,
                    assessment.model_dump_json(),
                ),
            )
        self._invalidate_storage_cache()

    def list_ai_assessments(self, limit: int = 1_000) -> list[AiCriticAssessment]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM ai_critic_assessments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [AiCriticAssessment.model_validate_json(row[0]) for row in rows]

    def unresolved_ai_assessments(self, limit: int = 500) -> list[AiCriticAssessment]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM ai_critic_assessments "
                "WHERE resolved_at IS NULL ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
        return [AiCriticAssessment.model_validate_json(row[0]) for row in rows]

    def prune_ai_assessments(self, max_resolved: int = 5_000) -> int:
        """Bound completed AI audits while never deleting an outcome still being measured."""

        if max_resolved < 1:
            raise ValueError("max_resolved must be positive")
        with self._lock, self._conn:
            removed = self._conn.execute(
                """DELETE FROM ai_critic_assessments
                   WHERE resolved_at IS NOT NULL AND assessment_id NOT IN (
                       SELECT assessment_id FROM ai_critic_assessments
                       WHERE resolved_at IS NOT NULL
                       ORDER BY created_at DESC LIMIT ?
                   )""",
                (max_resolved,),
            ).rowcount
        self._invalidate_storage_cache()
        return max(0, removed)

    def save_coach_review(self, review: CoachReview) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO coach_reviews VALUES(?,?,?,?,?,?)",
                (
                    review.review_id,
                    review.created_at.isoformat(),
                    review.risk_mode.value,
                    review.configuration_fingerprint,
                    int(review.valid),
                    review.model_dump_json(),
                ),
            )
        self._invalidate_storage_cache()

    def list_coach_reviews(self, limit: int = 100) -> list[CoachReview]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM coach_reviews ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [CoachReview.model_validate_json(row[0]) for row in rows]

    def save_coach_hypothesis(self, hypothesis: CoachHypothesis) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO coach_hypotheses VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(hypothesis_id) DO UPDATE SET
                   state=excluded.state,record_json=excluded.record_json""",
                (
                    hypothesis.hypothesis_id,
                    hypothesis.created_at.isoformat(),
                    hypothesis.state.value,
                    hypothesis.kind.value,
                    hypothesis.risk_mode.value,
                    hypothesis.configuration_fingerprint,
                    hypothesis.model_dump_json(),
                ),
            )
        self._invalidate_storage_cache()

    def list_coach_hypotheses(self, limit: int = 100) -> list[CoachHypothesis]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM coach_hypotheses ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [CoachHypothesis.model_validate_json(row[0]) for row in rows]

    def recent_learning_observations(self, limit: int = 1_000) -> list[LearningObservation]:
        if limit < 1:
            return []
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM learning_observations ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [LearningObservation.model_validate_json(row[0]) for row in reversed(rows)]

    def prune_coach_history(
        self,
        max_reviews: int = 250,
        max_hypotheses: int = 100,
    ) -> dict[str, int]:
        """Bound advisory artifacts without touching trading or learning evidence."""

        if max_reviews < 1 or max_hypotheses < 1:
            raise ValueError("coach retention limits must be positive")
        with self._lock, self._conn:
            reviews = self._conn.execute(
                """DELETE FROM coach_reviews WHERE review_id NOT IN (
                       SELECT review_id FROM coach_reviews ORDER BY created_at DESC LIMIT ?
                   )""",
                (max_reviews,),
            ).rowcount
            hypotheses = self._conn.execute(
                """DELETE FROM coach_hypotheses WHERE hypothesis_id NOT IN (
                       SELECT hypothesis_id FROM coach_hypotheses
                       ORDER BY created_at DESC LIMIT ?
                   )""",
                (max_hypotheses,),
            ).rowcount
        self._invalidate_storage_cache()
        return {"reviews": max(0, reviews), "hypotheses": max(0, hypotheses)}

    def record_incident(
        self,
        *,
        scope: str,
        severity: str,
        title: str,
        detail: str,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> OperationalIncident:
        observed_at = now or datetime.now().astimezone()
        with self._lock, self._conn:
            row = self._conn.execute(
                """SELECT record_json FROM operational_incidents
                   WHERE scope=? AND title=? AND resolved_at IS NULL
                   ORDER BY last_seen_at DESC LIMIT 1""",
                (scope, title),
            ).fetchone()
            if row is None:
                incident = OperationalIncident(
                    incident_id=uuid.uuid4().hex,
                    scope=scope[:80],
                    severity=severity[:20],
                    title=title[:160],
                    detail=detail[:500],
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                    occurrences=1,
                    metadata=metadata or {},
                )
                self._conn.execute(
                    "INSERT INTO operational_incidents VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        incident.incident_id,
                        incident.scope,
                        incident.severity,
                        incident.title,
                        incident.first_seen_at.isoformat(),
                        incident.last_seen_at.isoformat(),
                        incident.occurrences,
                        None,
                        incident.model_dump_json(),
                    ),
                )
            else:
                previous = OperationalIncident.model_validate_json(row[0])
                incident = previous.model_copy(
                    update={
                        "severity": severity[:20],
                        "detail": detail[:500],
                        "last_seen_at": observed_at,
                        "occurrences": previous.occurrences + 1,
                        "metadata": metadata or previous.metadata,
                    }
                )
                self._conn.execute(
                    """UPDATE operational_incidents SET severity=?,last_seen_at=?,
                       occurrences=?,record_json=? WHERE incident_id=?""",
                    (
                        incident.severity,
                        incident.last_seen_at.isoformat(),
                        incident.occurrences,
                        incident.model_dump_json(),
                        incident.incident_id,
                    ),
                )
        self._invalidate_storage_cache()
        return incident

    def record_transient_incident(
        self,
        *,
        scope: str,
        severity: str,
        title: str,
        detail: str,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
        coalesce_seconds: int = 3_600,
    ) -> OperationalIncident:
        """Save a recovered event in history without presenting it as a current outage.

        Short self-healing reconnects and traffic bursts remain auditable, but repeated episodes
        inside the coalescing window update one history row instead of flooding the status panel.
        """

        if coalesce_seconds < 0:
            raise ValueError("coalesce_seconds must not be negative")
        observed_at = now or datetime.now().astimezone()
        normalized_scope = scope[:80]
        normalized_title = title[:160]
        normalized_severity = severity[:20]
        normalized_detail = detail[:500]
        cutoff = observed_at - timedelta(seconds=coalesce_seconds)
        with self._lock, self._conn:
            row = self._conn.execute(
                """SELECT record_json FROM operational_incidents
                   WHERE scope=? AND title=? AND resolved_at IS NOT NULL
                   ORDER BY last_seen_at DESC LIMIT 1""",
                (normalized_scope, normalized_title),
            ).fetchone()
            previous = OperationalIncident.model_validate_json(row[0]) if row else None
            if previous is not None and previous.last_seen_at >= cutoff:
                incident = previous.model_copy(
                    update={
                        "severity": normalized_severity,
                        "detail": normalized_detail,
                        "last_seen_at": observed_at,
                        "occurrences": previous.occurrences + 1,
                        "resolved_at": observed_at,
                        "metadata": metadata or previous.metadata,
                    }
                )
                self._conn.execute(
                    """UPDATE operational_incidents SET severity=?,last_seen_at=?,
                       occurrences=?,resolved_at=?,record_json=? WHERE incident_id=?""",
                    (
                        incident.severity,
                        incident.last_seen_at.isoformat(),
                        incident.occurrences,
                        observed_at.isoformat(),
                        incident.model_dump_json(),
                        incident.incident_id,
                    ),
                )
            else:
                incident = OperationalIncident(
                    incident_id=uuid.uuid4().hex,
                    scope=normalized_scope,
                    severity=normalized_severity,
                    title=normalized_title,
                    detail=normalized_detail,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                    occurrences=1,
                    resolved_at=observed_at,
                    metadata=metadata or {},
                )
                self._conn.execute(
                    "INSERT INTO operational_incidents VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        incident.incident_id,
                        incident.scope,
                        incident.severity,
                        incident.title,
                        incident.first_seen_at.isoformat(),
                        incident.last_seen_at.isoformat(),
                        incident.occurrences,
                        observed_at.isoformat(),
                        incident.model_dump_json(),
                    ),
                )
        self._invalidate_storage_cache()
        return incident

    def resolve_incidents(self, scope: str, now: datetime | None = None) -> int:
        resolved_at = now or datetime.now().astimezone()
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT incident_id,record_json FROM operational_incidents "
                "WHERE scope=? AND resolved_at IS NULL",
                (scope,),
            ).fetchall()
            for row in rows:
                incident = OperationalIncident.model_validate_json(row[1]).model_copy(
                    update={"resolved_at": resolved_at}
                )
                self._conn.execute(
                    "UPDATE operational_incidents SET resolved_at=?,record_json=? "
                    "WHERE incident_id=?",
                    (resolved_at.isoformat(), incident.model_dump_json(), row[0]),
                )
        return len(rows)

    def list_incidents(self, limit: int = 100) -> list[OperationalIncident]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM operational_incidents "
                "ORDER BY resolved_at IS NULL DESC,last_seen_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [OperationalIncident.model_validate_json(row[0]) for row in rows]

    def prune_incidents(self, max_records: int = 2_000) -> int:
        with self._lock, self._conn:
            removed = self._conn.execute(
                """DELETE FROM operational_incidents WHERE incident_id IN (
                       SELECT incident_id FROM operational_incidents
                       WHERE resolved_at IS NOT NULL ORDER BY last_seen_at DESC
                       LIMIT -1 OFFSET ?
                   )""",
                (max_records,),
            ).rowcount
        return max(0, removed)

    def save_order(self, order: PaperOrder) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO paper_orders VALUES(?,?,?,?,?,?)
                   ON CONFLICT(order_id) DO UPDATE SET status=excluded.status,
                   record_json=excluded.record_json""",
                (
                    order.order_id,
                    order.mint,
                    order.side.value,
                    order.status.value,
                    order.created_at.isoformat(),
                    order.model_dump_json(),
                ),
            )

    def list_orders(self, statuses: Sequence[str] | None = None) -> list[PaperOrder]:
        with self._reader_lock:
            if statuses:
                marks = ",".join("?" for _ in statuses)
                # Only placeholder count is interpolated; every status remains parameterized.
                rows = self._reader_conn.execute(
                    f"SELECT record_json FROM paper_orders WHERE status IN ({marks}) "  # noqa: S608
                    "ORDER BY created_at",
                    tuple(statuses),
                ).fetchall()
            else:
                rows = self._reader_conn.execute(
                    "SELECT record_json FROM paper_orders ORDER BY created_at DESC"
                ).fetchall()
        return [PaperOrder.model_validate_json(row[0]) for row in rows]

    def save_fill(self, fill: FillReceipt) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO fills VALUES(?,?,?,?,?,?)",
                (
                    fill.fill_id,
                    fill.order_id,
                    fill.mint,
                    fill.side.value,
                    fill.filled_at.isoformat(),
                    fill.model_dump_json(),
                ),
            )

    def list_fills(self, limit: int = 200) -> list[FillReceipt]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM fills ORDER BY filled_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [FillReceipt.model_validate_json(row[0]) for row in rows]

    def save_position(self, position: Position) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO positions VALUES(?,?,?,?)
                   ON CONFLICT(position_id) DO UPDATE SET record_json=excluded.record_json""",
                (
                    position.position_id,
                    position.mint,
                    position.opened_at.isoformat(),
                    position.model_dump_json(),
                ),
            )

    def delete_position(self, position_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM positions WHERE position_id=?", (position_id,))

    def list_positions(self) -> list[Position]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT record_json FROM positions ORDER BY opened_at"
            ).fetchall()
        return [Position.model_validate_json(row[0]) for row in rows]

    def append_ledger(self, tx_id: str, entries: Iterable[tuple[str, int, int, str]]) -> None:
        rows = self._validated_ledger_entries(entries)
        now = datetime.now().astimezone().isoformat()
        with self._lock, self._conn:
            self._insert_ledger(tx_id, now, rows)

    def commit_buy_fill(
        self,
        order: PaperOrder,
        fill: FillReceipt,
        position: Position,
        entries: Iterable[tuple[str, int, int, str]],
    ) -> None:
        """Atomically persist every durable effect of one filled paper buy."""
        rows = self._validated_ledger_entries(entries)
        self._validate_fill_commit(order, fill)
        now = fill.filled_at.isoformat()
        with self._lock, self._conn:
            self._require_pending_order(order.order_id)
            self._update_filled_order(order)
            self._insert_fill(fill)
            self._insert_ledger(fill.fill_id, now, rows)
            self._conn.execute(
                "INSERT INTO positions VALUES(?,?,?,?)",
                (
                    position.position_id,
                    position.mint,
                    position.opened_at.isoformat(),
                    position.model_dump_json(),
                ),
            )

    def commit_sell_fill(
        self,
        order: PaperOrder,
        fill: FillReceipt,
        position: Position,
        entries: Iterable[tuple[str, int, int, str]],
        realized_pnl_lamports: int,
    ) -> None:
        """Atomically persist every durable effect of one filled paper sell."""
        rows = self._validated_ledger_entries(entries)
        self._validate_fill_commit(order, fill)
        now = fill.filled_at.isoformat()
        with self._lock, self._conn:
            self._require_pending_order(order.order_id)
            self._update_filled_order(order)
            self._insert_fill(fill)
            self._insert_ledger(fill.fill_id, now, rows)
            deleted = self._conn.execute(
                "DELETE FROM positions WHERE position_id=?", (position.position_id,)
            ).rowcount
            if deleted != 1:
                raise RuntimeError("paper position disappeared during sell commit")
            self._conn.execute(
                """INSERT INTO settings(key, value_json, updated_at) VALUES(?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                   updated_at=excluded.updated_at""",
                (
                    "realized_pnl_lamports",
                    json.dumps(realized_pnl_lamports, separators=(",", ":")),
                    now,
                ),
            )

    @staticmethod
    def _validated_ledger_entries(
        entries: Iterable[tuple[str, int, int, str]],
    ) -> list[tuple[str, int, int, str]]:
        rows = list(entries)
        if not rows or sum(x[1] for x in rows) != sum(x[2] for x in rows):
            raise ValueError("ledger transaction is not balanced")
        if any(debit < 0 or credit < 0 for _, debit, credit, _ in rows):
            raise ValueError("ledger entries cannot be negative")
        return rows

    def _insert_ledger(
        self,
        tx_id: str,
        created_at: str,
        rows: list[tuple[str, int, int, str]],
    ) -> None:
        self._conn.executemany(
            """INSERT INTO ledger_entries(
                tx_id,created_at,account,debit_lamports,credit_lamports,memo)
                VALUES(?,?,?,?,?,?)""",
            [(tx_id, created_at, *entry) for entry in rows],
        )

    @staticmethod
    def _validate_fill_commit(order: PaperOrder, fill: FillReceipt) -> None:
        if order.order_id != fill.order_id or order.status.value != "filled":
            raise ValueError("fill commit requires its matching filled order")

    def _require_pending_order(self, order_id: str) -> None:
        row = self._conn.execute(
            "SELECT status FROM paper_orders WHERE order_id=?", (order_id,)
        ).fetchone()
        if row is None or row[0] != "pending":
            raise RuntimeError("paper order is no longer pending")

    def _update_filled_order(self, order: PaperOrder) -> None:
        self._conn.execute(
            "UPDATE paper_orders SET status=?, record_json=? WHERE order_id=?",
            (order.status.value, order.model_dump_json(), order.order_id),
        )

    def _insert_fill(self, fill: FillReceipt) -> None:
        self._conn.execute(
            "INSERT INTO fills VALUES(?,?,?,?,?,?)",
            (
                fill.fill_id,
                fill.order_id,
                fill.mint,
                fill.side.value,
                fill.filled_at.isoformat(),
                fill.model_dump_json(),
            ),
        )

    def ledger_balance(self, account: str) -> int:
        with self._reader_lock:
            row = self._reader_conn.execute(
                """SELECT COALESCE(SUM(debit_lamports-credit_lamports),0)
                   FROM ledger_entries WHERE account=?""",
                (account,),
            ).fetchone()
        return int(row[0])

    def increment_provider_usage(self, provider: str, month: str) -> int:
        now = datetime.now().astimezone().isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO provider_usage(provider,month,calls,updated_at) VALUES(?,?,1,?)
                   ON CONFLICT(provider,month) DO UPDATE SET
                   calls=calls+1,updated_at=excluded.updated_at""",
                (provider, month, now),
            )
            row = self._conn.execute(
                "SELECT calls FROM provider_usage WHERE provider=? AND month=?",
                (provider, month),
            ).fetchone()
        return int(row[0])

    def provider_usage(self, month: str) -> dict[str, int]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                "SELECT provider,calls FROM provider_usage WHERE month=?", (month,)
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def record_equity(
        self,
        equity_lamports: int,
        cash_lamports: int,
        *,
        recorded_at: datetime | None = None,
    ) -> None:
        observed_at = recorded_at or datetime.now().astimezone()
        now = observed_at.isoformat()
        bucket = observed_at.replace(minute=0, second=0, microsecond=0).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO equity_points(
                    recorded_at,equity_lamports,cash_lamports) VALUES(?,?,?)""",
                (now, equity_lamports, cash_lamports),
            )
            self._conn.execute(
                """INSERT INTO equity_rollups VALUES(?,?,?,?,?,?,1)
                   ON CONFLICT(bucket_start) DO UPDATE SET
                   high_equity_lamports=MAX(high_equity_lamports,excluded.high_equity_lamports),
                   low_equity_lamports=MIN(low_equity_lamports,excluded.low_equity_lamports),
                   close_equity_lamports=excluded.close_equity_lamports,
                   close_cash_lamports=excluded.close_cash_lamports,
                   samples=samples+1""",
                (
                    bucket,
                    equity_lamports,
                    equity_lamports,
                    equity_lamports,
                    equity_lamports,
                    cash_lamports,
                ),
            )

    def equity_history(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._reader_lock:
            rows = self._reader_conn.execute(
                """SELECT recorded_at,equity_lamports,cash_lamports FROM equity_points
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def max_recorded_cash(self) -> int:
        """Return the highest durable cash observation for the current paper season."""

        with self._reader_lock:
            detailed = self._reader_conn.execute(
                "SELECT COALESCE(MAX(cash_lamports),0) FROM equity_points"
            ).fetchone()[0]
            rolled_up = self._reader_conn.execute(
                "SELECT COALESCE(MAX(close_cash_lamports),0) FROM equity_rollups"
            ).fetchone()[0]
        return max(0, int(detailed), int(rolled_up))

    def compact_equity_history(
        self,
        *,
        recent_limit: int = 500,
        rollup_limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return detailed recent equity plus hourly close points for long-running seasons."""

        recent = self.equity_history(recent_limit)
        oldest = (
            str(recent[0]["recorded_at"]) if recent else datetime.now().astimezone().isoformat()
        )
        with self._reader_lock:
            rows = self._reader_conn.execute(
                """SELECT bucket_start AS recorded_at,
                          close_equity_lamports AS equity_lamports,
                          close_cash_lamports AS cash_lamports
                   FROM equity_rollups WHERE bucket_start<?
                   ORDER BY bucket_start DESC LIMIT ?""",
                (oldest, rollup_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)] + recent

    def reset_paper_state(self, season_summary: dict[str, Any] | None = None) -> None:
        """Archive the active season, then delete only its virtual portfolio state."""
        now = datetime.now().astimezone().isoformat()
        with self._lock, self._conn:
            initialized_row = self._conn.execute(
                "SELECT value_json FROM settings WHERE key='portfolio_initialized'"
            ).fetchone()
            initialized = bool(json.loads(initialized_row[0])) if initialized_row else False
            if initialized:
                season_row = self._conn.execute(
                    "SELECT value_json FROM settings WHERE key='season_id'"
                ).fetchone()
                season_id = json.loads(season_row[0]) if season_row else None
                if not season_id:
                    raise RuntimeError("initialized paper portfolio has no season id")
                if season_summary is None:
                    raise RuntimeError("active paper season must be summarized before reset")
                self._archive_active_season(str(season_id), season_summary, now)
            self._clear_paper_tables()
            self._upsert_settings(
                [
                    ("portfolio_initialized", False),
                    ("starting_lamports", 0),
                    ("realized_pnl_lamports", 0),
                    ("peak_equity_lamports", 0),
                    ("equity_peak_basis", None),
                    ("trading_enabled", False),
                    ("season_id", None),
                    ("auto_new_season_eligible_since", None),
                ],
                now,
            )

    def rollover_paper_state(
        self,
        *,
        season_summary: dict[str, Any],
        next_season_id: str,
        starting_minor: int,
        quote_currency: str,
        rolled_over_at: datetime,
    ) -> None:
        """Atomically finish one season and create its like-for-like successor."""

        if starting_minor <= 0:
            raise ValueError("starting bankroll must be positive")
        now = rolled_over_at.isoformat()
        with self._lock, self._conn:
            initialized_row = self._conn.execute(
                "SELECT value_json FROM settings WHERE key='portfolio_initialized'"
            ).fetchone()
            if not initialized_row or not bool(json.loads(initialized_row[0])):
                raise RuntimeError("automatic rollover requires an initialized portfolio")
            season_row = self._conn.execute(
                "SELECT value_json FROM settings WHERE key='season_id'"
            ).fetchone()
            previous_season_id = json.loads(season_row[0]) if season_row else None
            if not previous_season_id:
                raise RuntimeError("initialized paper portfolio has no season id")

            self._archive_active_season(str(previous_season_id), season_summary, now)
            self._clear_paper_tables()
            self._insert_ledger(
                next_season_id,
                now,
                [
                    ("cash", starting_minor, 0, "Automatic season bankroll"),
                    ("capital", 0, starting_minor, "Automatic season bankroll"),
                ],
            )
            self._upsert_settings(
                [
                    ("portfolio_initialized", True),
                    ("quote_currency", quote_currency),
                    ("starting_lamports", starting_minor),
                    ("realized_pnl_lamports", 0),
                    ("peak_equity_lamports", starting_minor),
                    ("equity_peak_basis", "executable-route-v1"),
                    ("trading_enabled", True),
                    ("season_id", next_season_id),
                    ("auto_new_season_eligible_since", None),
                    ("auto_new_season_last_rollover_at", now),
                    ("auto_new_season_last_from", str(previous_season_id)),
                    ("auto_new_season_last_to", next_season_id),
                ],
                now,
            )
            self._insert_current_season(
                season_id=next_season_id,
                started_at=now,
                quote_currency=quote_currency,
                starting_minor=starting_minor,
            )
            self._conn.execute(
                """INSERT INTO equity_points(
                    recorded_at,equity_lamports,cash_lamports) VALUES(?,?,?)""",
                (now, starting_minor, starting_minor),
            )

    def _archive_active_season(
        self,
        season_id: str,
        season_summary: dict[str, Any],
        ended_at: str,
    ) -> None:
        updated = self._conn.execute(
            """UPDATE paper_seasons SET
                   ended_at=?,ending_equity_minor=?,last_known_ending_equity_minor=?,
                   peak_equity_minor=?,realized_pnl_minor=?,net_pnl_minor=?,
                   total_fees_minor=?,closed_trades=?,wins=?,losses=?,break_even=?,
                   ending_drawdown_fraction=?,open_positions=?,status='completed'
               WHERE season_id=? AND status='current'""",
            (
                ended_at,
                int(season_summary["ending_equity_minor"]),
                int(season_summary["last_known_ending_equity_minor"]),
                int(season_summary["peak_equity_minor"]),
                int(season_summary["realized_pnl_minor"]),
                int(season_summary["net_pnl_minor"]),
                int(season_summary["total_fees_minor"]),
                int(season_summary["closed_trades"]),
                int(season_summary["wins"]),
                int(season_summary["losses"]),
                int(season_summary["break_even"]),
                max(0.0, min(1.0, float(season_summary["ending_drawdown_fraction"]))),
                int(season_summary["open_positions"]),
                season_id,
            ),
        ).rowcount
        if updated != 1:
            raise RuntimeError("active paper season summary row is missing")

    def _clear_paper_tables(self) -> None:
        for table in (
            "fills",
            "paper_orders",
            "positions",
            "ledger_entries",
            "equity_points",
            "equity_rollups",
            "decisions",
        ):
            self._conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed names only
