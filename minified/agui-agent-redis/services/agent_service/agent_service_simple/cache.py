from __future__ import annotations

import os
from typing import Protocol
from urllib.parse import quote

from agent_service_simple.models import AgentRunRequest, ThreadCacheEntry, utc_now_iso

DEFAULT_KEY_PREFIX = "agui:min:v1"


class RedisClientProtocol(Protocol):
    async def get(self, key: str) -> bytes | str | None: ...

    async def set(self, key: str, value: str, *, ex: int | None = None) -> object: ...


class RedisThreadCache:
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

    async def upsert_from_run(self, request: AgentRunRequest) -> tuple[str, ThreadCacheEntry]:
        key = thread_cache_key(
            user_id=request.user.user_id,
            thread_id=request.thread_id,
            prefix=self._key_prefix,
        )
        existing = await self.get(key)
        entry = ThreadCacheEntry(
            user_id=request.user.user_id,
            thread_id=request.thread_id,
            session_id=request.session_id,
            agent_session_id=request.session_id or request.thread_id,
            token_ref=request.user.token_ref,
            messages=[message.model_dump(mode="json") for message in request.messages],
            state={**(existing.state if existing else {}), **request.state},
            run_count=(existing.run_count if existing else 0) + 1,
            updated_at=utc_now_iso(),
        )
        await self._redis.set(key, entry.model_dump_json(), ex=self._ttl_seconds)
        return key, entry

    async def get(self, key: str) -> ThreadCacheEntry | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return ThreadCacheEntry.model_validate_json(raw)


def build_thread_cache() -> RedisThreadCache:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is required")

    from redis.asyncio import from_url as redis_from_url

    return RedisThreadCache(
        redis_from_url(redis_url),
        ttl_seconds=_optional_int_env("AGENT_SERVICE_STORE_TTL_SECONDS"),
    )


def thread_cache_key(*, user_id: str, thread_id: str, prefix: str = DEFAULT_KEY_PREFIX) -> str:
    return f"{prefix}:user:{_encode(user_id)}:thread:{_encode(thread_id)}"


def _encode(value: str) -> str:
    if not value:
        raise ValueError("Redis key parts must not be empty")
    return quote(value, safe="")


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)
