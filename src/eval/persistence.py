"""SQLite persistence for eval runs."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class RunManifest(BaseModel):
    run_id: str
    timestamp: str
    corpus_version: int
    ground_truth_version: str = "labels.json"
    repo: str = "digitalocean/doctl"
    model_a: str
    model_b: str
    concurrency: int
    prompt_version: str
    status: str = "running"
    completed: int = 0
    total: int = 0
    failed: int = 0
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    metrics_path: str = "metrics.json"
    sampled_issue_ids: list[str] = Field(default_factory=list)


class FunnelRun(BaseModel):
    """Persisted result of a 4-stage model-selection funnel run."""

    funnel_id: str
    timestamp: str
    status: str = "running"  # running | complete | aborted | failed
    stage_reached: int = 0  # 1-4; 0 means not started
    pilot_model_slugs: list[str] = Field(default_factory=list)
    full_model_slugs: list[str] = Field(default_factory=list)
    recommended_a: str | None = None
    recommended_b: str | None = None
    rationale: str = ""
    elimination_summary: dict = Field(default_factory=dict)
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None


class RunStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    model_a TEXT NOT NULL,
                    model_b TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    manifest_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_issues (
                    run_id TEXT NOT NULL,
                    issue_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    predicted_label TEXT,
                    status TEXT NOT NULL,
                    latency_ms REAL,
                    cost_usd REAL,
                    PRIMARY KEY (run_id, issue_id, model)
                );
                CREATE TABLE IF NOT EXISTS funnel_runs (
                    funnel_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage_reached INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    funnel_json TEXT NOT NULL
                );
                """
            )

    def upsert_funnel(self, funnel: FunnelRun) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO funnel_runs (
                    funnel_id, timestamp, status, stage_reached, started_at, finished_at, funnel_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(funnel_id) DO UPDATE SET
                    status=excluded.status,
                    stage_reached=excluded.stage_reached,
                    finished_at=excluded.finished_at,
                    funnel_json=excluded.funnel_json
                """,
                (
                    funnel.funnel_id,
                    funnel.timestamp,
                    funnel.status,
                    funnel.stage_reached,
                    funnel.started_at,
                    funnel.finished_at,
                    funnel.model_dump_json(),
                ),
            )

    def get_funnel(self, funnel_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT funnel_json FROM funnel_runs WHERE funnel_id = ?",
                (funnel_id,),
            ).fetchone()
        return json.loads(row["funnel_json"]) if row else None

    def list_funnels(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT funnel_json FROM funnel_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["funnel_json"]) for row in rows]

    def upsert_run(self, manifest: RunManifest) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, timestamp, repo, model_a, model_b, status,
                    completed, total, failed, started_at, finished_at, manifest_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    completed=excluded.completed,
                    total=excluded.total,
                    failed=excluded.failed,
                    finished_at=excluded.finished_at,
                    manifest_json=excluded.manifest_json
                """,
                (
                    manifest.run_id,
                    manifest.timestamp,
                    manifest.repo,
                    manifest.model_a,
                    manifest.model_b,
                    manifest.status,
                    manifest.completed,
                    manifest.total,
                    manifest.failed,
                    manifest.started_at,
                    manifest.finished_at,
                    manifest.model_dump_json(),
                ),
            )

    def list_runs(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT manifest_json FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["manifest_json"]) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT manifest_json FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["manifest_json"]) if row else None

    def paginate_issues(
        self,
        run_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
        disagreement_only: bool = False,
        model_a: str | None = None,
        model_b: str | None = None,
        dataset_filter: str = "all",
        scored_ids: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        with self._connect() as conn:
            filter_sql = ""
            params = []
            if dataset_filter == "scored" and scored_ids:
                placeholders = ",".join(["?"] * len(scored_ids))
                filter_sql = f"AND a.issue_id IN ({placeholders})"
                params = list(scored_ids)
            elif dataset_filter == "unscored" and scored_ids:
                placeholders = ",".join(["?"] * len(scored_ids))
                filter_sql = f"AND a.issue_id NOT IN ({placeholders})"
                params = list(scored_ids)

            if disagreement_only and model_a and model_b:
                rows = conn.execute(
                    f"""
                    SELECT a.issue_id,
                           a.predicted_label AS label_a,
                           b.predicted_label AS label_b,
                           a.latency_ms AS latency_a,
                           b.latency_ms AS latency_b,
                           a.cost_usd AS cost_a,
                           b.cost_usd AS cost_b
                    FROM run_issues a
                    JOIN run_issues b
                      ON a.run_id = b.run_id AND a.issue_id = b.issue_id
                    WHERE a.run_id = ?
                      AND a.model = ?
                      AND b.model = ?
                      AND COALESCE(a.predicted_label, '') != COALESCE(b.predicted_label, '')
                      {filter_sql}
                    ORDER BY a.issue_id
                    LIMIT ? OFFSET ?
                    """,
                    (run_id, model_a, model_b, *params, limit, offset),
                ).fetchall()
                total = conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM run_issues a
                    JOIN run_issues b
                      ON a.run_id = b.run_id AND a.issue_id = b.issue_id
                    WHERE a.run_id = ?
                      AND a.model = ?
                      AND b.model = ?
                      AND COALESCE(a.predicted_label, '') != COALESCE(b.predicted_label, '')
                      {filter_sql}
                    """,
                    (run_id, model_a, model_b, *params),
                ).fetchone()[0]
            else:
                raw_filter = filter_sql.replace("a.issue_id", "issue_id")
                rows = conn.execute(
                    f"""
                    SELECT issue_id,
                           MAX(CASE WHEN model = ? THEN predicted_label END) AS label_a,
                           MAX(CASE WHEN model = ? THEN predicted_label END) AS label_b,
                           MAX(CASE WHEN model = ? THEN latency_ms END) AS latency_a,
                           MAX(CASE WHEN model = ? THEN latency_ms END) AS latency_b,
                           MAX(CASE WHEN model = ? THEN cost_usd END) AS cost_a,
                           MAX(CASE WHEN model = ? THEN cost_usd END) AS cost_b,
                           MAX(CASE WHEN model = ? THEN status END) AS status_a,
                           MAX(CASE WHEN model = ? THEN status END) AS status_b
                    FROM run_issues
                    WHERE run_id = ?
                      {raw_filter}
                    GROUP BY issue_id
                    ORDER BY issue_id
                    LIMIT ? OFFSET ?
                    """,
                    (
                        model_a,
                        model_b,
                        model_a,
                        model_b,
                        model_a,
                        model_b,
                        model_a,
                        model_b,
                        run_id,
                        *params,
                        limit,
                        offset,
                    ),
                ).fetchall()
                total = conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT issue_id) FROM run_issues
                    WHERE run_id = ?
                      {raw_filter}
                    """,
                    (run_id, *params),
                ).fetchone()[0]
        return [dict(row) for row in rows], int(total)

    def index_predictions(self, run_id: str, predictions_path: Path) -> None:
        if not predictions_path.exists():
            return
        with self._connect() as conn, predictions_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                conn.execute(
                    """
                    INSERT INTO run_issues (
                        run_id, issue_id, model, predicted_label, status, latency_ms, cost_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, issue_id, model) DO UPDATE SET
                        predicted_label=excluded.predicted_label,
                        status=excluded.status,
                        latency_ms=excluded.latency_ms,
                        cost_usd=excluded.cost_usd
                    """,
                    (
                        run_id,
                        row["issue_id"],
                        row["model"],
                        row.get("predicted_label"),
                        row["status"],
                        row.get("latency_ms"),
                        row.get("cost_usd"),
                    ),
                )
