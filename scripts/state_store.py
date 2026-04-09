#!/usr/bin/env python3
"""
Persistent lifecycle store for AI-DAN Factory.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIFECYCLE_STATES = {
    "idea",
    "validated",
    "scored",
    "approved",
    "rejected",
    "hold",
    "building",
    "deployed",
    "monitored",
    "scaled",
    "killed",
}

# Strict state-machine:
# idea -> validated -> scored -> approved/rejected/hold
# approved -> building -> deployed -> monitored -> scaled/killed
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "idea": {"validated"},
    "validated": {"scored"},
    "scored": {"approved", "rejected", "hold"},
    "approved": {"building"},
    "building": {"deployed"},
    "deployed": {"monitored"},
    "monitored": {"scaled", "killed"},
    "rejected": set(),
    "hold": set(),
    "scaled": set(),
    "killed": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StageTransitionError(Exception):
    pass


class FactoryStateStore:
    def __init__(self, db_path: str):
        path = Path(db_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    @staticmethod
    def _run_key(run_id: str, run_attempt: str) -> str:
        return f"{run_id}:{run_attempt}"

    def _init_db(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_key TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              run_attempt TEXT NOT NULL,
              project_id TEXT NOT NULL,
              state TEXT NOT NULL,
              decision TEXT DEFAULT '',
              score REAL DEFAULT NULL,
              run_mode TEXT DEFAULT '',
              repo_url TEXT DEFAULT '',
              deployment_url TEXT DEFAULT '',
              workflow_url TEXT DEFAULT '',
              failure_reason TEXT DEFAULT '',
              error_summary TEXT DEFAULT '',
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
              updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_unique
            ON runs(run_id, run_attempt);

            CREATE TABLE IF NOT EXISTS transitions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_key TEXT NOT NULL,
              run_id TEXT NOT NULL,
              run_attempt TEXT NOT NULL,
              project_id TEXT NOT NULL,
              from_state TEXT NOT NULL,
              to_state TEXT NOT NULL,
              status TEXT NOT NULL,
              reason TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(run_key) REFERENCES runs(run_key) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_transitions_run_key ON transitions(run_key);
            CREATE INDEX IF NOT EXISTS idx_transitions_project ON transitions(project_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS monitoring_signals (
              run_key TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              run_attempt TEXT NOT NULL,
              project_id TEXT NOT NULL,
              traffic_signal TEXT NOT NULL,
              activation_metric TEXT NOT NULL,
              revenue_signal_status TEXT NOT NULL,
              portfolio_decision TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(run_key) REFERENCES runs(run_key) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_monitoring_project ON monitoring_signals(project_id, updated_at DESC);
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def initialize_run(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        initial_state: str = "idea",
        workflow_url: str = "",
        run_mode: str | None = None,
    ) -> None:
        state = initial_state.strip().lower()
        if state not in LIFECYCLE_STATES:
            raise StageTransitionError(f"Invalid initial state '{initial_state}'")
        existing = self.get_run(run_id, run_attempt)
        if existing is not None:
            # Keep existing state unless explicitly re-seeding same state.
            if str(existing["state"]).strip().lower() != state:
                raise StageTransitionError(
                    f"Run already initialized at state '{existing['state']}', cannot reset to '{state}'."
                )
            return
        self._upsert_run(
            run_id=run_id,
            run_attempt=run_attempt,
            project_id=project_id,
            state=state,
            workflow_url=workflow_url,
            run_mode=run_mode,
        )

    def get_run(self, run_id: str, run_attempt: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE run_id = ? AND run_attempt = ?",
            (run_id, run_attempt),
        ).fetchone()
        if row is None:
            return None
        return {k: row[k] for k in row.keys()}

    def get_current_state(self, project_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE project_id = ? ORDER BY updated_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return {k: row[k] for k in row.keys()}

    def list_recent_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]

    def _upsert_run(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        state: str,
        decision: str | None = None,
        score: float | None = None,
        run_mode: str | None = None,
        repo_url: str | None = None,
        deployment_url: str | None = None,
        workflow_url: str | None = None,
        failure_reason: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        run_key = self._run_key(run_id, run_attempt)
        now = utc_now()
        existing = self.get_run(run_id, run_attempt)

        if existing is None:
            self.conn.execute(
                """
                INSERT INTO runs (
                  run_key, run_id, run_attempt, project_id, state, decision, score, run_mode,
                  repo_url, deployment_url, workflow_url, failure_reason, error_summary, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_key,
                    run_id,
                    run_attempt,
                    project_id,
                    state,
                    decision or "",
                    score,
                    run_mode or "",
                    repo_url or "",
                    deployment_url or "",
                    workflow_url or "",
                    failure_reason or "",
                    error_summary or "",
                    now,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE runs
                SET project_id = ?,
                    state = ?,
                    decision = ?,
                    score = ?,
                    run_mode = ?,
                    repo_url = ?,
                    deployment_url = ?,
                    workflow_url = ?,
                    failure_reason = ?,
                    error_summary = ?,
                    updated_at = ?
                WHERE run_key = ?
                """,
                (
                    project_id,
                    state,
                    existing["decision"] if decision is None else decision,
                    existing["score"] if score is None else score,
                    existing["run_mode"] if run_mode is None else run_mode,
                    existing["repo_url"] if repo_url is None else repo_url,
                    existing["deployment_url"] if deployment_url is None else deployment_url,
                    existing["workflow_url"] if workflow_url is None else workflow_url,
                    existing["failure_reason"] if failure_reason is None else failure_reason,
                    existing["error_summary"] if error_summary is None else error_summary,
                    now,
                    run_key,
                ),
            )
        self.conn.commit()

    def _append_transition(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        from_state: str,
        to_state: str,
        status: str,
        reason: str,
        timestamp_utc: str,
        metadata: dict[str, Any],
    ) -> None:
        run_key = self._run_key(run_id, run_attempt)
        self.conn.execute(
            """
            INSERT INTO transitions (
              run_key, run_id, run_attempt, project_id, from_state, to_state, status,
              reason, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_key,
                run_id,
                run_attempt,
                project_id,
                from_state,
                to_state,
                status,
                reason,
                json.dumps(metadata, ensure_ascii=True),
                timestamp_utc,
            ),
        )
        self.conn.commit()

    def record_transition(
        self,
        *,
        project_id: str,
        from_state: str,
        to_state: str,
        status: str,
        reason: str,
        run_id: str,
        run_attempt: str,
        workflow_url: str,
        timestamp_utc: str,
        metadata: dict[str, Any] | None = None,
        decision: str | None = None,
        score: float | None = None,
        run_mode: str | None = None,
        repo_url: str | None = None,
        deployment_url: str | None = None,
        failure_reason: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        from_state = from_state.strip().lower()
        to_state = to_state.strip().lower()
        if from_state not in LIFECYCLE_STATES:
            raise StageTransitionError(f"Invalid from_state '{from_state}'")
        if to_state not in LIFECYCLE_STATES:
            raise StageTransitionError(f"Invalid to_state '{to_state}'")

        run = self.get_run(run_id, run_attempt)
        if run is None:
            # First transition must originate from idea.
            if from_state != "idea":
                raise StageTransitionError("First transition for a run must start from 'idea'")
            self._upsert_run(
                run_id=run_id,
                run_attempt=run_attempt,
                project_id=project_id,
                state=from_state,
                workflow_url=workflow_url,
                run_mode=run_mode,
            )
            # Allow explicit run initialization event (idea -> idea).
            if to_state == "idea":
                self._append_transition(
                    run_id=run_id,
                    run_attempt=run_attempt,
                    project_id=project_id,
                    from_state="idea",
                    to_state="idea",
                    status=status,
                    reason=reason,
                    timestamp_utc=timestamp_utc,
                    metadata=metadata or {},
                )
                return
            run = self.get_run(run_id, run_attempt)
            if run is None:
                raise StageTransitionError("Failed to initialize run state.")

        current_state = str(run["state"]).strip().lower()
        if current_state != from_state:
            raise StageTransitionError(
                f"Transition mismatch: current state is '{current_state}', but from_state was '{from_state}'."
            )

        allowed = ALLOWED_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise StageTransitionError(f"Invalid lifecycle transition '{from_state}' -> '{to_state}'")

        self._upsert_run(
            run_id=run_id,
            run_attempt=run_attempt,
            project_id=project_id,
            state=to_state,
            decision=decision,
            score=score,
            run_mode=run_mode,
            repo_url=repo_url,
            deployment_url=deployment_url,
            workflow_url=workflow_url,
            failure_reason=failure_reason,
            error_summary=error_summary,
        )
        self._append_transition(
            run_id=run_id,
            run_attempt=run_attempt,
            project_id=project_id,
            from_state=from_state,
            to_state=to_state,
            status=status,
            reason=reason,
            timestamp_utc=timestamp_utc,
            metadata=metadata or {},
        )

    def list_transitions(self, run_id: str, run_attempt: str) -> list[dict[str, Any]]:
        run_key = self._run_key(run_id, run_attempt)
        rows = self.conn.execute(
            "SELECT * FROM transitions WHERE run_key = ? ORDER BY id ASC",
            (run_key,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = {k: row[k] for k in row.keys()}
            try:
                item["metadata"] = json.loads(item.pop("metadata_json"))
            except json.JSONDecodeError:
                item["metadata"] = {}
                item.pop("metadata_json", None)
            out.append(item)
        return out

    def upsert_monitoring_signal(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        traffic_signal: str,
        activation_metric: str,
        revenue_signal_status: str,
        portfolio_decision: str,
    ) -> None:
        run_key = self._run_key(run_id, run_attempt)
        now = utc_now()
        row = self.conn.execute(
            "SELECT run_key FROM monitoring_signals WHERE run_key = ?",
            (run_key,),
        ).fetchone()
        if row is None:
            self.conn.execute(
                """
                INSERT INTO monitoring_signals (
                  run_key, run_id, run_attempt, project_id, traffic_signal, activation_metric,
                  revenue_signal_status, portfolio_decision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_key,
                    run_id,
                    run_attempt,
                    project_id,
                    traffic_signal,
                    activation_metric,
                    revenue_signal_status,
                    portfolio_decision,
                    now,
                    now,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE monitoring_signals
                SET project_id = ?,
                    traffic_signal = ?,
                    activation_metric = ?,
                    revenue_signal_status = ?,
                    portfolio_decision = ?,
                    updated_at = ?
                WHERE run_key = ?
                """,
                (
                    project_id,
                    traffic_signal,
                    activation_metric,
                    revenue_signal_status,
                    portfolio_decision,
                    now,
                    run_key,
                ),
            )
        self.conn.commit()

    def list_monitoring_signals(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM monitoring_signals ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]


class StateStore:
    """
    Compatibility wrapper used by scripts that expect explicit run transitions.
    """

    def __init__(self, db_path: str):
        self._store = FactoryStateStore(db_path)

    def get_run_state(self, run_id: str, run_attempt: str) -> str | None:
        run = self._store.get_run(run_id, run_attempt)
        return None if run is None else str(run["state"])

    def upsert_run(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        state: str,
        updated_at: str,
    ) -> None:
        _ = updated_at
        self._store._upsert_run(
            run_id=run_id,
            run_attempt=run_attempt,
            project_id=project_id,
            state=state,
        )

    def insert_event(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        from_state: str,
        to_state: str,
        status: str,
        reason: str,
        created_at: str,
        metadata: dict[str, Any],
    ) -> None:
        self._store._append_transition(
            run_id=run_id,
            run_attempt=run_attempt,
            project_id=project_id,
            from_state=from_state,
            to_state=to_state,
            status=status,
            reason=reason,
            timestamp_utc=created_at,
            metadata=metadata,
        )

    def transition(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        to_state: str,
        reason: str,
        metadata: dict[str, Any],
        timestamp_utc: str,
    ) -> None:
        run = self._store.get_run(run_id, run_attempt)
        if run is None:
            raise StageTransitionError("Cannot transition without existing run record.")
        from_state = str(run["state"]).strip().lower()
        self._store.record_transition(
            project_id=project_id,
            from_state=from_state,
            to_state=to_state,
            status="success" if to_state not in {"rejected", "hold", "killed"} else "failed",
            reason=reason,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow_url=str(run.get("workflow_url", "")),
            timestamp_utc=timestamp_utc,
            metadata=metadata,
        )

    def record_monitoring_signal(
        self,
        *,
        run_id: str,
        run_attempt: str,
        project_id: str,
        traffic_signal: str,
        activation_metric: str,
        revenue_signal_status: str,
        portfolio_decision: str,
        timestamp_utc: str,
    ) -> None:
        _ = timestamp_utc
        self._store.upsert_monitoring_signal(
            run_id=run_id,
            run_attempt=run_attempt,
            project_id=project_id,
            traffic_signal=traffic_signal,
            activation_metric=activation_metric,
            revenue_signal_status=revenue_signal_status,
            portfolio_decision=portfolio_decision,
        )

    def list_monitoring_signals(self, limit: int = 500) -> list[dict[str, Any]]:
        return self._store.list_monitoring_signals(limit=limit)
