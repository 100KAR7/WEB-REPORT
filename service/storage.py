"""SQLite persistence for audit runs."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator


class RunStore:
    """Minimal SQLite-backed store for run metadata and outputs."""

    def __init__(self, db_path: str = "data/app.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT
                )
                """
            )

    def create_run(self, target_url: str, config: dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO runs (target_url, status, created_at, updated_at, config_json)
                VALUES (?, 'queued', ?, ?, ?)
                """,
                (target_url, now, now, json.dumps(config)),
            )
            return int(cur.lastrowid)

    def mark_running(self, run_id: int) -> None:
        self._update_status(run_id, "running")

    def mark_completed(self, run_id: int, result: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = 'completed', updated_at = ?, result_json = ?, error = NULL
                WHERE id = ?
                """,
                (now, json.dumps(result), run_id),
            )

    def mark_failed(self, run_id: int, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = 'failed', updated_at = ?, error = ?
                WHERE id = ?
                """,
                (now, error[:4000], run_id),
            )

    def _update_status(self, run_id: int, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, run_id),
            )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        result_json = row["result_json"]
        config_json = row["config_json"]
        return {
            "id": row["id"],
            "target_url": row["target_url"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "config": json.loads(config_json) if config_json else {},
            "result": json.loads(result_json) if result_json else None,
            "error": row["error"],
        }
