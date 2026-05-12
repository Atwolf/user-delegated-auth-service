from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from typing import Protocol, TypeVar, cast
from urllib.parse import quote

from pydantic import BaseModel
from session_state import build_session_key, build_thread_key, build_workflow_key

from .models import (
    PlanWorkflowRequest,
    SessionRecord,
    ThreadRecord,
    TokenRegistryRecord,
    WorkflowRecord,
    utc_now,
)

AGENT_SERVICE_KEY_PREFIX = "agent_service:v1"

StateModelT = TypeVar("StateModelT", bound=BaseModel)


@dataclass(frozen=True)
class SessionScope:
    user_id: str
    session_id: str
    tenant_id: str | None = None


class RedisClientProtocol(Protocol):
    async def get(self, key: str) -> bytes | str | None: ...

    async def set(self, key: str, value: str, *, ex: int | None = None) -> object: ...


class AgentServiceStore(Protocol):
    async def upsert_session(self, request: PlanWorkflowRequest) -> SessionRecord: ...

    async def save_workflow(self, record: WorkflowRecord) -> WorkflowRecord: ...

    async def get_workflow(
        self,
        *,
        workflow_id: str,
        user_id: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> WorkflowRecord | None: ...

    async def register_auth_context(
        self,
        record: TokenRegistryRecord,
    ) -> TokenRegistryRecord: ...

    async def get_auth_context(
        self,
        *,
        user_id: str,
        session_id: str,
        token_ref: str,
        tenant_id: str | None = None,
    ) -> str | None: ...

    async def save_thread(self, record: ThreadRecord) -> ThreadRecord: ...

    async def get_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> ThreadRecord | None: ...


class InMemoryAgentServiceStore:
    """Process-local Agent Service store for explicitly injected tests."""

    def __init__(self) -> None:
        self._sessions: dict[SessionScope, SessionRecord] = {}
        self._workflows: dict[tuple[str | None, str, str, str], WorkflowRecord] = {}
        self._tokens: dict[tuple[str | None, str, str, str], TokenRegistryRecord] = {}
        self._threads: dict[tuple[str | None, str, str, str], ThreadRecord] = {}
        self._lock = Lock()

    async def upsert_session(self, request: PlanWorkflowRequest) -> SessionRecord:
        record = _session_record_for_request(request)
        with self._lock:
            self._sessions[_session_scope(record)] = record

        if record.auth_context_ref and record.token_ref:
            await self.register_auth_context(
                TokenRegistryRecord(
                    user_id=record.user_id,
                    session_id=record.session_id,
                    tenant_id=record.tenant_id,
                    token_ref=record.token_ref,
                    auth_context_ref=record.auth_context_ref,
                )
            )
        return record

    async def save_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        with self._lock:
            self._workflows[_workflow_identity(record)] = record
        return record

    async def get_workflow(
        self,
        *,
        workflow_id: str,
        user_id: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> WorkflowRecord | None:
        with self._lock:
            return self._workflows.get((tenant_id, user_id, session_id, workflow_id))

    async def register_auth_context(
        self,
        record: TokenRegistryRecord,
    ) -> TokenRegistryRecord:
        with self._lock:
            self._tokens[_token_identity(record)] = record
        return record

    async def get_auth_context(
        self,
        *,
        user_id: str,
        session_id: str,
        token_ref: str,
        tenant_id: str | None = None,
    ) -> str | None:
        with self._lock:
            record = self._tokens.get((tenant_id, user_id, session_id, token_ref))
        return None if record is None else record.auth_context_ref

    async def save_thread(self, record: ThreadRecord) -> ThreadRecord:
        with self._lock:
            self._threads[_thread_identity(record)] = record
        return record

    async def get_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> ThreadRecord | None:
        with self._lock:
            return self._threads.get((tenant_id, user_id, session_id, thread_id))


class RedisAgentServiceStore:
    """Redis-backed Agent Service store."""

    def __init__(
        self,
        redis: RedisClientProtocol,
        *,
        key_prefix: str = AGENT_SERVICE_KEY_PREFIX,
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    async def upsert_session(self, request: PlanWorkflowRequest) -> SessionRecord:
        record = _session_record_for_request(request)
        await self._set(key=self._session_key(record), value=record)
        if record.auth_context_ref and record.token_ref:
            await self.register_auth_context(
                TokenRegistryRecord(
                    user_id=record.user_id,
                    session_id=record.session_id,
                    tenant_id=record.tenant_id,
                    token_ref=record.token_ref,
                    auth_context_ref=record.auth_context_ref,
                )
            )
        return record

    async def save_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        await self._set(
            key=self._workflow_key(
                tenant_id=record.tenant_id,
                user_id=record.user_id,
                session_id=record.session_id,
                workflow_id=record.workflow_id,
            ),
            value=record,
        )
        return record

    async def get_workflow(
        self,
        *,
        workflow_id: str,
        user_id: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> WorkflowRecord | None:
        key = self._workflow_key(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            workflow_id=workflow_id,
        )
        return await self._get(key=key, model_type=WorkflowRecord)

    async def register_auth_context(
        self,
        record: TokenRegistryRecord,
    ) -> TokenRegistryRecord:
        await self._set(
            key=self._token_key(
                tenant_id=record.tenant_id,
                user_id=record.user_id,
                session_id=record.session_id,
                token_ref=record.token_ref,
            ),
            value=record,
        )
        return record

    async def get_auth_context(
        self,
        *,
        user_id: str,
        session_id: str,
        token_ref: str,
        tenant_id: str | None = None,
    ) -> str | None:
        key = self._token_key(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            token_ref=token_ref,
        )
        raw = await self._redis.get(key)
        if raw is None:
            return None
        record = TokenRegistryRecord.model_validate_json(_decode_json_blob(raw))
        return record.auth_context_ref

    async def save_thread(self, record: ThreadRecord) -> ThreadRecord:
        await self._set(
            key=self._thread_key(
                tenant_id=record.tenant_id,
                user_id=record.user_id,
                session_id=record.session_id,
                thread_id=record.thread_id,
            ),
            value=record,
        )
        return record

    async def get_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> ThreadRecord | None:
        return await self._get(
            key=self._thread_key(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                thread_id=thread_id,
            ),
            model_type=ThreadRecord,
        )

    async def _set(
        self,
        *,
        key: str,
        value: BaseModel,
    ) -> None:
        await self._redis.set(key, value.model_dump_json(), ex=self._ttl_seconds)

    async def _get(
        self,
        *,
        key: str,
        model_type: type[StateModelT],
    ) -> StateModelT | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return model_type.model_validate_json(_decode_json_blob(raw))

    def _session_key(self, record: SessionRecord) -> str:
        return build_session_key(
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            session_id=record.session_id,
            prefix=self._key_prefix,
        )

    def _workflow_key(
        self,
        *,
        tenant_id: str | None,
        user_id: str,
        session_id: str,
        workflow_id: str,
    ) -> str:
        return build_workflow_key(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            workflow_id=workflow_id,
            prefix=self._key_prefix,
        )

    def _thread_key(
        self,
        *,
        tenant_id: str | None,
        user_id: str,
        session_id: str,
        thread_id: str,
    ) -> str:
        return build_thread_key(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            thread_id=thread_id,
            prefix=self._key_prefix,
        )

    def _token_key(
        self,
        *,
        tenant_id: str | None,
        user_id: str,
        session_id: str,
        token_ref: str,
    ) -> str:
        session_key = build_session_key(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            prefix=self._key_prefix,
        )
        return f"{session_key}:token:{quote(token_ref, safe='')}"


def build_agent_service_store() -> AgentServiceStore:
    backend = os.getenv("AGENT_SERVICE_STATE_BACKEND", "redis").strip().lower()
    if backend not in {"memory", "redis"}:
        raise RuntimeError("AGENT_SERVICE_STATE_BACKEND must be memory or redis")

    if backend == "memory":
        if os.getenv("AGENT_SERVICE_ENABLE_TEST_MEMORY_STATE") != "true":
            raise RuntimeError(
                "AGENT_SERVICE_STATE_BACKEND=memory is only available for explicit tests"
            )
        return InMemoryAgentServiceStore()

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is required when AGENT_SERVICE_STATE_BACKEND=redis")

    from redis.asyncio import from_url as redis_from_url

    redis_client = cast(RedisClientProtocol, redis_from_url(redis_url))
    return RedisAgentServiceStore(
        redis_client,
        ttl_seconds=_optional_int_env("AGENT_SERVICE_STORE_TTL_SECONDS"),
    )


def make_token_ref(
    *,
    user_id: str,
    session_id: str,
    tenant_id: str | None,
    auth_context_ref: str,
) -> str:
    material = "\x1f".join((tenant_id or "", user_id, session_id, auth_context_ref))
    return f"token:{sha256(material.encode()).hexdigest()[:24]}"


def _token_ref_for_request(request: PlanWorkflowRequest) -> str | None:
    if request.token_ref:
        return request.token_ref
    if not request.auth_context_ref:
        return None
    return make_token_ref(
        user_id=request.user_id,
        session_id=request.session_id,
        tenant_id=request.tenant_id,
        auth_context_ref=request.auth_context_ref,
    )


def _session_record_for_request(request: PlanWorkflowRequest) -> SessionRecord:
    return SessionRecord(
        user_id=request.user_id,
        session_id=request.session_id,
        token_ref=_token_ref_for_request(request),
        auth_context_ref=request.auth_context_ref,
        token_scopes=request.token_scopes,
        allowed_tools=request.allowed_tools,
        tenant_id=request.tenant_id,
        updated_at=utc_now(),
    )


def _session_scope(record: SessionRecord) -> SessionScope:
    return SessionScope(
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        session_id=record.session_id,
    )


def _workflow_identity(record: WorkflowRecord) -> tuple[str | None, str, str, str]:
    return (record.tenant_id, record.user_id, record.session_id, record.workflow_id)


def _token_identity(record: TokenRegistryRecord) -> tuple[str | None, str, str, str]:
    return (record.tenant_id, record.user_id, record.session_id, record.token_ref)


def _thread_identity(record: ThreadRecord) -> tuple[str | None, str, str, str]:
    return (record.tenant_id, record.user_id, record.session_id, record.thread_id)


def _decode_json_blob(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return raw


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)


InMemoryStateStore = InMemoryAgentServiceStore
