from __future__ import annotations

import os

from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata, utc_now_iso
from adk_agent_service.stores.thread_metadata import (
    DEFAULT_KEY_PREFIX,
    RedisClientProtocol,
    thread_metadata_key,
)


class RedisThreadMetadataStore:
    def __init__(
        self,
        redis: RedisClientProtocol,
        *,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    async def upsert_from_run(self, request: AgentRunRequest) -> tuple[str, ThreadRunMetadata]:
        key = thread_metadata_key(
            user_id=request.user.user_id,
            thread_id=request.thread_id,
            prefix=self._key_prefix,
        )
        metadata = ThreadRunMetadata(
            user_id=request.user.user_id,
            thread_id=request.thread_id,
            session_id=request.session_id,
            agent_session_id=request.session_id or request.thread_id,
            updated_at=utc_now_iso(),
        )
        await self._redis.set(key, metadata.model_dump_json(), ex=self._ttl_seconds)
        return key, metadata


def build_thread_metadata_store() -> RedisThreadMetadataStore:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is required")

    from redis.asyncio import from_url as redis_from_url

    return RedisThreadMetadataStore(
        redis_from_url(redis_url),
        ttl_seconds=optional_int_env("AGENT_SERVICE_STORE_TTL_SECONDS"),
    )


def optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)
