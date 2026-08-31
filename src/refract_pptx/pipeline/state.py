from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class StageReceipt:
    item_id: str
    stage: str
    status: StageStatus
    input_hash: str
    output: dict[str, Any]
    error: str
    updated_at: str


class RunState:
    """Small transactional state store for resumable, multi-process runs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stage_receipts (
                    item_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    output_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (item_id, stage)
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
    def _now() -> str:
        return datetime.now(tz=UTC).isoformat()

    def start(self, item_id: str, stage: str, input_hash: str) -> bool:
        """Claim a stage. Returns False when an identical completed stage is reusable."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, input_hash FROM stage_receipts WHERE item_id=? AND stage=?",
                (item_id, stage),
            ).fetchone()
            if row == (StageStatus.COMPLETE.value, input_hash):
                return False
            connection.execute(
                """
                INSERT INTO stage_receipts
                    (item_id, stage, status, input_hash, output_json, error, updated_at)
                VALUES (?, ?, ?, ?, '{}', '', ?)
                ON CONFLICT(item_id, stage) DO UPDATE SET
                    status=excluded.status,
                    input_hash=excluded.input_hash,
                    output_json='{}',
                    error='',
                    updated_at=excluded.updated_at
                """,
                (item_id, stage, StageStatus.RUNNING.value, input_hash, self._now()),
            )
        return True

    def complete(self, item_id: str, stage: str, output: dict[str, Any]) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE stage_receipts
                SET status=?, output_json=?, error='', updated_at=?
                WHERE item_id=? AND stage=? AND status=?
                """,
                (
                    StageStatus.COMPLETE.value,
                    json.dumps(output, sort_keys=True),
                    self._now(),
                    item_id,
                    stage,
                    StageStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"stage is not running: {item_id}/{stage}")

    def fail(self, item_id: str, stage: str, error: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE stage_receipts
                SET status=?, error=?, updated_at=?
                WHERE item_id=? AND stage=?
                """,
                (StageStatus.FAILED.value, error, self._now(), item_id, stage),
            )

    def receipt(self, item_id: str, stage: str) -> StageReceipt | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT item_id, stage, status, input_hash, output_json, error, updated_at
                FROM stage_receipts WHERE item_id=? AND stage=?
                """,
                (item_id, stage),
            ).fetchone()
        if row is None:
            return None
        return StageReceipt(
            item_id=row[0],
            stage=row[1],
            status=StageStatus(row[2]),
            input_hash=row[3],
            output=json.loads(row[4]),
            error=row[5],
            updated_at=row[6],
        )
