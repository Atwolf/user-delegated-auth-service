from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata

DEFAULT_KEY_PREFIX = "agui:agent:v1"


class RedisClientProtocol(Protocol):
    async def set(self, key: str, value: str, *, ex: int | None = None) -> object: ...


class ThreadMetadataStore(Protocol):
    async def upsert_from_run(self, request: AgentRunRequest) -> tuple[str, ThreadRunMetadata]: ...


def thread_metadata_key(
    *,
    user_id: str,
    thread_id: str,
    prefix: str = DEFAULT_KEY_PREFIX,
) -> str:
    return f"{prefix}:user:{encode_key_part(user_id)}:thread:{encode_key_part(thread_id)}"


def encode_key_part(value: str) -> str:
    if not value:
        raise ValueError("Redis key parts must not be empty")
    return quote(value, safe="")
