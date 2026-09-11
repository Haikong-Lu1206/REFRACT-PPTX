from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class TaskRegistration:
    task_id: str
    source_sha256: str
    design_key: str
    created_at: str


class TaskRegistry:
    """Transactional, stable task-ID allocation for concurrent batch workers."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_registry (
                    task_id TEXT PRIMARY KEY,
                    source_sha256 TEXT NOT NULL,
                    design_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_sha256, design_key)
                )
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _validate_digest(value: str) -> str:
        digest = value.lower().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("source_sha256 must be a 64-character hexadecimal digest")
        return digest

    @staticmethod
    def _validate_task_id(value: str) -> str:
        task_id = value.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", task_id):
            raise ValueError("task_id must be a 3-80 character lowercase slug")
        return task_id

    def allocate(
        self,
        source_sha256: str,
        design_key: str,
        *,
        prefix: str = "refract",
        width: int = 6,
        requested_id: str | None = None,
    ) -> str:
        digest = self._validate_digest(source_sha256)
        key = design_key.strip()
        if not key:
            raise ValueError("design_key is required")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", prefix):
            raise ValueError("prefix must be a lowercase slug")
        if width < 3 or width > 12:
            raise ValueError("width must be between 3 and 12")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT task_id FROM task_registry
                WHERE source_sha256=? AND design_key=?
                """,
                (digest, key),
            ).fetchone()
            if existing:
                if requested_id and existing[0] != requested_id:
                    raise ValueError(
                        f"source/design already registered as {existing[0]}, not {requested_id}"
                    )
                return str(existing[0])
            if requested_id:
                task_id = self._validate_task_id(requested_id)
            else:
                rows = connection.execute(
                    "SELECT task_id FROM task_registry WHERE task_id LIKE ?",
                    (f"{prefix}-%",),
                ).fetchall()
                pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
                numbers = [int(match.group(1)) for row in rows if (match := pattern.match(row[0]))]
                task_id = f"{prefix}-{max(numbers, default=0) + 1:0{width}d}"
            collision = connection.execute(
                "SELECT source_sha256, design_key FROM task_registry WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if collision:
                raise ValueError(f"task_id is already assigned: {task_id}")
            connection.execute(
                """
                INSERT INTO task_registry(task_id, source_sha256, design_key, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, digest, key, datetime.now(tz=UTC).isoformat()),
            )
        return task_id

    def registrations(self) -> tuple[TaskRegistration, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT task_id, source_sha256, design_key, created_at
                FROM task_registry ORDER BY task_id
                """
            ).fetchall()
        return tuple(TaskRegistration(*row) for row in rows)


__all__ = ["TaskRegistration", "TaskRegistry"]
