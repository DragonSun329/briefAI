"""
Pipeline Run Store

Persists pipeline execution history (runs, stages, events) to SQLite.
Enables: debugging failed runs, comparing output quality over time,
and building historical baselines for trend analysis.

Usage:
    store = RunStore()
    run_id = store.create_run("news", {"days_back": 7})
    store.update_stage(run_id, "scrape", "completed", items_in=0, items_out=150)
    store.complete_run(run_id, "completed", articles_scraped=150, articles_selected=10)
    
    # Query
    runs = store.list_runs(pipeline_id="news", limit=10)
    run = store.get_run(run_id)
"""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from pipeline.base import PipelineEvent, PipelineResult, PipelineStatus, StageResult


DB_PATH = Path(__file__).parent.parent / "data" / "pipeline_runs.db"


class RunStore:
    """SQLite-backed storage for pipeline run history."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    pipeline_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    execution_time REAL,
                    articles_scraped INTEGER DEFAULT 0,
                    articles_selected INTEGER DEFAULT 0,
                    report_path TEXT,
                    error TEXT,
                    config_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_runs_pipeline
                    ON pipeline_runs(pipeline_id);
                CREATE INDEX IF NOT EXISTS idx_runs_status
                    ON pipeline_runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_started
                    ON pipeline_runs(started_at DESC);

                CREATE TABLE IF NOT EXISTS pipeline_stages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    duration_s REAL,
                    items_in INTEGER DEFAULT 0,
                    items_out INTEGER DEFAULT 0,
                    error TEXT,
                    metadata_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_stages_run
                    ON pipeline_stages(run_id);

                CREATE TABLE IF NOT EXISTS pipeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    stage TEXT,
                    message TEXT,
                    progress REAL,
                    data_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_events_run
                    ON pipeline_events(run_id);
            """)

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def create_run(
        self,
        pipeline_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new pipeline run. Returns run_id."""
        run_id = str(uuid.uuid4())[:12]
        now = time.time()

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO pipeline_runs (run_id, pipeline_id, status, started_at, config_json)
                   VALUES (?, ?, 'running', ?, ?)""",
                (run_id, pipeline_id, now, json.dumps(config or {})),
            )

        logger.info(f"Created pipeline run {run_id} for {pipeline_id}")
        return run_id

    def complete_run(self, run_id: str, result: PipelineResult) -> None:
        """Mark a run as completed with its result."""
        now = time.time()

        with self._conn() as conn:
            conn.execute(
                """UPDATE pipeline_runs
                   SET status = ?,
                       completed_at = ?,
                       execution_time = ?,
                       articles_scraped = ?,
                       articles_selected = ?,
                       report_path = ?,
                       error = ?,
                       metadata_json = ?
                   WHERE run_id = ?""",
                (
                    result.status.value,
                    now,
                    result.execution_time,
                    result.articles_scraped,
                    result.articles_selected,
                    result.report_path,
                    result.error,
                    json.dumps(result.metadata),
                    run_id,
                ),
            )

            # Persist stages
            for stage in result.stages:
                conn.execute(
                    """INSERT INTO pipeline_stages
                       (run_id, stage, status, started_at, duration_s, items_in, items_out, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        stage.stage,
                        stage.status.value,
                        now - stage.duration_s,
                        stage.duration_s,
                        stage.items_in,
                        stage.items_out,
                        stage.error,
                    ),
                )

        logger.info(f"Completed run {run_id}: {result.status.value}")

    def fail_run(self, run_id: str, error: str) -> None:
        """Mark a run as failed."""
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """UPDATE pipeline_runs
                   SET status = 'failed', completed_at = ?, error = ?
                   WHERE run_id = ?""",
                (now, error, run_id),
            )

    # ------------------------------------------------------------------
    # Event logging
    # ------------------------------------------------------------------

    def log_event(self, run_id: str, event: PipelineEvent) -> None:
        """Persist a pipeline event."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO pipeline_events
                   (run_id, event_type, timestamp, stage, message, progress, data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    event.event_type.value,
                    event.timestamp,
                    event.stage,
                    event.message,
                    event.progress,
                    json.dumps(event.data) if event.data else None,
                ),
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a single run with its stages."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if not row:
                return None

            run = dict(row)
            run["config"] = json.loads(run.pop("config_json", "{}") or "{}")
            run["metadata"] = json.loads(run.pop("metadata_json", "{}") or "{}")

            stages = conn.execute(
                "SELECT * FROM pipeline_stages WHERE run_id = ? ORDER BY started_at",
                (run_id,),
            ).fetchall()
            run["stages"] = [dict(s) for s in stages]

            return run

    def list_runs(
        self,
        pipeline_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List runs with optional filters."""
        query = "SELECT * FROM pipeline_runs WHERE 1=1"
        params: List[Any] = []

        if pipeline_id:
            query += " AND pipeline_id = ?"
            params.append(pipeline_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            runs = []
            for row in rows:
                r = dict(row)
                r["config"] = json.loads(r.pop("config_json", "{}") or "{}")
                r["metadata"] = json.loads(r.pop("metadata_json", "{}") or "{}")
                runs.append(r)
            return runs

    def get_events(
        self,
        run_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get events for a run."""
        query = "SELECT * FROM pipeline_events WHERE run_id = ?"
        params: List[Any] = [run_id]

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY timestamp LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            events = []
            for row in rows:
                e = dict(row)
                e["data"] = json.loads(e.pop("data_json", "{}") or "{}")
                events.append(e)
            return events

    def get_stats(self, pipeline_id: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        """Get aggregate stats for pipeline runs."""
        cutoff = time.time() - (days * 86400)

        with self._conn() as conn:
            where = "WHERE started_at > ?"
            params: List[Any] = [cutoff]
            if pipeline_id:
                where += " AND pipeline_id = ?"
                params.append(pipeline_id)

            row = conn.execute(
                f"""SELECT
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    AVG(execution_time) as avg_time,
                    AVG(articles_scraped) as avg_scraped,
                    AVG(articles_selected) as avg_selected,
                    MAX(started_at) as last_run
                FROM pipeline_runs {where}""",
                params,
            ).fetchone()

            return dict(row) if row else {}

    def cleanup(self, keep_days: int = 90) -> int:
        """Delete runs older than keep_days. Returns count deleted."""
        cutoff = time.time() - (keep_days * 86400)
        with self._conn() as conn:
            # Get run IDs to delete
            run_ids = [
                r["run_id"]
                for r in conn.execute(
                    "SELECT run_id FROM pipeline_runs WHERE started_at < ?", (cutoff,)
                ).fetchall()
            ]
            if not run_ids:
                return 0

            placeholders = ",".join(["?"] * len(run_ids))
            conn.execute(f"DELETE FROM pipeline_events WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM pipeline_stages WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM pipeline_runs WHERE run_id IN ({placeholders})", run_ids)

            logger.info(f"Cleaned up {len(run_ids)} old pipeline runs")
            return len(run_ids)
