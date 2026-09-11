from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


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
    attempts: int = 0
    owner: str = ""
    lease_until: str = ""


class RunState:
    """Small transactional state store for resumable, multi-process runs."""

    def __init__(self, path: str | Path, *, default_lease_seconds: int = 900):
        self.path = Path(path)
        self._owners = threading.local()
        self.default_lease_seconds = max(30, int(default_lease_seconds))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
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
                    attempts INTEGER NOT NULL DEFAULT 0,
                    owner TEXT NOT NULL DEFAULT '',
                    lease_until TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (item_id, stage)
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(stage_receipts)")}
            for name, declaration in (
                ("attempts", "INTEGER NOT NULL DEFAULT 0"),
                ("owner", "TEXT NOT NULL DEFAULT ''"),
                ("lease_until", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE stage_receipts ADD COLUMN {name} {declaration}"
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

    @staticmethod
    def _default_owner() -> str:
        return f"{socket.gethostname()}:{os.getpid()}"

    def start(
        self,
        item_id: str,
        stage: str,
        input_hash: str,
        *,
        owner: str | None = None,
        lease_seconds: int | None = None,
    ) -> bool:
        """Claim a stage.

        Returns ``False`` when an identical result is reusable or another live
        worker owns the stage. Expired ``running`` rows are reclaimed.
        """
        worker = owner or f"{self._default_owner()}:{uuid4().hex}"
        now = datetime.now(tz=UTC)
        lease = now + timedelta(seconds=lease_seconds or self.default_lease_seconds)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, input_hash, lease_until
                FROM stage_receipts WHERE item_id=? AND stage=?
                """,
                (item_id, stage),
            ).fetchone()
            if row and row[0] == StageStatus.COMPLETE.value and row[1] == input_hash:
                return False
            if row and row[0] == StageStatus.RUNNING.value:
                try:
                    live = bool(row[2]) and datetime.fromisoformat(row[2]) > now
                except (ValueError, TypeError):
                    live = False
                if live:
                    return False
            connection.execute(
                """
                INSERT INTO stage_receipts
                    (item_id, stage, status, input_hash, output_json, error, updated_at,
                     attempts, owner, lease_until)
                VALUES (?, ?, ?, ?, '{}', '', ?, 1, ?, ?)
                ON CONFLICT(item_id, stage) DO UPDATE SET
                    status=excluded.status,
                    input_hash=excluded.input_hash,
                    output_json='{}',
                    error='',
                    updated_at=excluded.updated_at,
                    attempts=stage_receipts.attempts + 1,
                    owner=excluded.owner,
                    lease_until=excluded.lease_until
                """,
                (
                    item_id,
                    stage,
                    StageStatus.RUNNING.value,
                    input_hash,
                    now.isoformat(),
                    worker,
                    lease.isoformat(),
                ),
            )
        if not hasattr(self._owners, "claims"):
            self._owners.claims = {}
        self._owners.claims[(item_id, stage)] = worker
        return True

    def _claim_owner(self, item_id: str, stage: str, owner: str | None) -> str:
        worker = owner or getattr(self._owners, "claims", {}).get((item_id, stage))
        if not worker:
            raise RuntimeError(f"no local stage claim: {item_id}/{stage}")
        return worker

    def heartbeat(
        self,
        item_id: str,
        stage: str,
        *,
        owner: str | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        worker = self._claim_owner(item_id, stage, owner)
        lease = datetime.now(tz=UTC) + timedelta(
            seconds=lease_seconds or self.default_lease_seconds
        )
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE stage_receipts SET updated_at=?, lease_until=?
                WHERE item_id=? AND stage=? AND status=? AND owner=?
                """,
                (
                    self._now(),
                    lease.isoformat(),
                    item_id,
                    stage,
                    StageStatus.RUNNING.value,
                    worker,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"stage lease is not owned by {worker}: {item_id}/{stage}")

    def complete(
        self, item_id: str, stage: str, output: dict[str, Any], *, owner: str | None = None
    ) -> None:
        worker = self._claim_owner(item_id, stage, owner)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE stage_receipts
                SET status=?, output_json=?, error='', updated_at=?, lease_until=''
                WHERE item_id=? AND stage=? AND status=? AND owner=?
                """,
                (
                    StageStatus.COMPLETE.value,
                    json.dumps(output, sort_keys=True),
                    self._now(),
                    item_id,
                    stage,
                    StageStatus.RUNNING.value,
                    worker,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"stage is not running: {item_id}/{stage}")

    def fail(self, item_id: str, stage: str, error: str, *, owner: str | None = None) -> None:
        worker = self._claim_owner(item_id, stage, owner)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE stage_receipts
                SET status=?, error=?, updated_at=?, lease_until=''
                WHERE item_id=? AND stage=? AND status=? AND owner=?
                """,
                (
                    StageStatus.FAILED.value,
                    error,
                    self._now(),
                    item_id,
                    stage,
                    StageStatus.RUNNING.value,
                    worker,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"stage lease is no longer owned: {item_id}/{stage}")

    def receipt(self, item_id: str, stage: str) -> StageReceipt | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT item_id, stage, status, input_hash, output_json, error, updated_at,
                       attempts, owner, lease_until
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
            attempts=int(row[7]),
            owner=row[8],
            lease_until=row[9],
        )

    def receipts(self, *, status: StageStatus | None = None) -> tuple[StageReceipt, ...]:
        query = """
            SELECT item_id, stage, status, input_hash, output_json, error, updated_at,
                   attempts, owner, lease_until
            FROM stage_receipts
        """
        parameters: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status=?"
            parameters = (status.value,)
        query += " ORDER BY item_id, stage"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(
            StageReceipt(
                item_id=row[0],
                stage=row[1],
                status=StageStatus(row[2]),
                input_hash=row[3],
                output=json.loads(row[4]),
                error=row[5],
                updated_at=row[6],
                attempts=int(row[7]),
                owner=row[8],
                lease_until=row[9],
            )
            for row in rows
        )

    def summary(self) -> dict[str, int]:
        counts = {status.value: 0 for status in StageStatus}
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM stage_receipts GROUP BY status"
            ).fetchall()
        counts.update({str(status): int(count) for status, count in rows})
        counts["total"] = sum(counts[status.value] for status in StageStatus)
        return counts

    def reset_failed(self, *, item_id: str | None = None) -> int:
        with self._connection() as connection:
            if item_id is None:
                cursor = connection.execute(
                    "DELETE FROM stage_receipts WHERE status=?",
                    (StageStatus.FAILED.value,),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM stage_receipts WHERE status=? AND item_id=?",
                    (StageStatus.FAILED.value, item_id),
                )
        return int(cursor.rowcount)

    def reset(self, item_id: str, stage: str) -> bool:
        """Forget one receipt after its declared artifact is missing or invalid."""
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM stage_receipts WHERE item_id=? AND stage=? AND status=?",
                (item_id, stage, StageStatus.COMPLETE.value),
            )
        return cursor.rowcount == 1
