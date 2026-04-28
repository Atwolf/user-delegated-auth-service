from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field

CREATE_SUBAGENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS subagents (
  agent_name TEXT PRIMARY KEY,
  base_url TEXT NOT NULL,
  mcp_server_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 100,
  updated_at TEXT NOT NULL
);
"""


class SubagentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    mcp_server_name: str = Field(..., min_length=1)
    enabled: bool = True
    priority: int = Field(default=100)
    updated_at: datetime


class SubagentDiscoveryService:
    """Async SQLite-backed registry for supervisor subagent discovery."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    async def create_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(CREATE_SUBAGENTS_TABLE_SQL)
            await db.commit()

    async def load_enabled_subagents(self) -> list[SubagentRecord]:
        await self.create_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                  agent_name,
                  base_url,
                  mcp_server_name,
                  enabled,
                  priority,
                  updated_at
                FROM subagents
                WHERE enabled = 1
                ORDER BY priority ASC, agent_name ASC
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()

        return [self._record_from_row(row) for row in rows]

    async def refresh_enabled_subagents(self) -> list[SubagentRecord]:
        return await self.load_enabled_subagents()

    async def upsert_subagent(self, record: SubagentRecord) -> SubagentRecord:
        await self.create_schema()
        normalized = record.model_copy(
            update={"updated_at": self._normalize_datetime(record.updated_at)}
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO subagents (
                  agent_name,
                  base_url,
                  mcp_server_name,
                  enabled,
                  priority,
                  updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_name) DO UPDATE SET
                  base_url = excluded.base_url,
                  mcp_server_name = excluded.mcp_server_name,
                  enabled = excluded.enabled,
                  priority = excluded.priority,
                  updated_at = excluded.updated_at
                """,
                (
                    normalized.agent_name,
                    normalized.base_url,
                    normalized.mcp_server_name,
                    int(normalized.enabled),
                    normalized.priority,
                    normalized.updated_at.isoformat(),
                ),
            )
            await db.commit()

        return normalized

    @staticmethod
    def _record_from_row(row: aiosqlite.Row) -> SubagentRecord:
        payload: dict[str, Any] = dict(row)
        payload["enabled"] = bool(payload["enabled"])
        return SubagentRecord.model_validate(payload)

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
