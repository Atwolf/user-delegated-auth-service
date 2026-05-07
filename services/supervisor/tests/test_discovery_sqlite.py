from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agent_service_supervisor.discovery_sqlite import (
    SubagentDiscoveryService,
    SubagentRecord,
)


def _record(
    agent_name: str,
    *,
    enabled: bool = True,
    priority: int = 100,
) -> SubagentRecord:
    return SubagentRecord(
        agent_name=agent_name,
        base_url=f"http://{agent_name}.internal:8080",
        mcp_server_name=f"{agent_name}-mcp",
        enabled=enabled,
        priority=priority,
        updated_at=datetime(2026, 4, 27, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_load_enabled_subagents_orders_by_priority_then_name(tmp_path) -> None:
    service = SubagentDiscoveryService(tmp_path / "subagents.sqlite")

    await service.upsert_subagent(_record("identity", priority=20))
    await service.upsert_subagent(_record("billing", priority=10))
    await service.upsert_subagent(_record("developer", priority=10))

    records = await service.load_enabled_subagents()

    assert [record.agent_name for record in records] == [
        "billing",
        "developer",
        "identity",
    ]
    assert all(isinstance(record, SubagentRecord) for record in records)


@pytest.mark.asyncio
async def test_load_enabled_subagents_excludes_disabled_records(tmp_path) -> None:
    service = SubagentDiscoveryService(tmp_path / "subagents.sqlite")

    await service.upsert_subagent(_record("developer", enabled=True))
    await service.upsert_subagent(_record("disabled", enabled=False, priority=1))

    records = await service.load_enabled_subagents()

    assert [record.agent_name for record in records] == ["developer"]
