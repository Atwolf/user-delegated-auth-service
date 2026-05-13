from __future__ import annotations

import logging
import os

from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata
from adk_agent_service.stores.in_memory_thread_metadata import InMemoryThreadMetadataStore
from adk_agent_service.stores.redis_thread_metadata import RedisThreadMetadataStore
from adk_agent_service.stores.thread_metadata import ThreadMetadataStore

logger = logging.getLogger(__name__)


class FallbackThreadMetadataStore:
    def __init__(
        self,
        primary: ThreadMetadataStore,
        fallback: ThreadMetadataStore,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    async def upsert_from_run(self, request: AgentRunRequest) -> tuple[str, ThreadRunMetadata]:
        try:
            return await self._primary.upsert_from_run(request)
        except Exception as exc:
            logger.warning("Thread metadata primary store failed; using in-memory store: %s", exc)
            return await self._fallback.upsert_from_run(request)


def build_thread_metadata_store() -> ThreadMetadataStore:
    mode = os.getenv("AGENT_SERVICE_METADATA_STORE", "auto").strip().casefold()
    allow_fallback = truthy_env("AGENT_SERVICE_ALLOW_IN_MEMORY_FALLBACK", default=True)

    if mode == "memory":
        return InMemoryThreadMetadataStore()
    if mode not in {"auto", "redis"}:
        raise RuntimeError("AGENT_SERVICE_METADATA_STORE must be one of: auto, redis, memory")

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        if mode == "redis":
            raise RuntimeError("REDIS_URL is required when AGENT_SERVICE_METADATA_STORE=redis")
        return InMemoryThreadMetadataStore()

    from redis.asyncio import from_url as redis_from_url

    redis_store = RedisThreadMetadataStore(
        redis_from_url(redis_url),
        ttl_seconds=optional_int_env("AGENT_SERVICE_STORE_TTL_SECONDS"),
    )
    if mode == "auto" and allow_fallback:
        return FallbackThreadMetadataStore(redis_store, InMemoryThreadMetadataStore())
    return redis_store


def optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)


def truthy_env(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}
