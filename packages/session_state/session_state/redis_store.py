from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel
from redis.exceptions import WatchError as RedisWatchError

from .interfaces import SessionIdentity, SessionStateStore, WorkflowEventLike
from .key_builder import (
    DEFAULT_KEY_PREFIX,
    build_session_events_key,
    build_session_key,
    build_workflow_events_key,
    build_workflow_key,
)
from .models import SessionState, WorkflowState

StateModelT = TypeVar("StateModelT", bound=BaseModel)


class RedisPipelineProtocol(Protocol):
    async def __aenter__(self) -> RedisPipelineProtocol: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    async def watch(self, key: str) -> object: ...

    async def get(self, key: str) -> bytes | str | None: ...

    def multi(self) -> None: ...

    def set(self, key: str, value: str, *, ex: int | None = None) -> object: ...

    async def execute(self) -> list[object]: ...

    async def reset(self) -> object: ...


class RedisClientProtocol(Protocol):
    async def get(self, key: str) -> bytes | str | None: ...

    async def set(self, key: str, value: str, *, ex: int | None = None) -> object: ...

    async def rpush(self, key: str, value: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> object: ...

    def pipeline(self, *, transaction: bool = True) -> RedisPipelineProtocol: ...


class SessionStateStoreError(RuntimeError):
    pass


class SessionStateNotFoundError(SessionStateStoreError):
    pass


class WorkflowStateNotFoundError(SessionStateStoreError):
    pass


class SessionStateVersionConflictError(SessionStateStoreError):
    pass


def _decode_json_blob(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return raw


class RedisSessionStateStore(SessionStateStore):
    """Redis-backed state store using Pydantic JSON blobs."""

    def __init__(
        self,
        redis: RedisClientProtocol,
        *,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        ttl_seconds: int | None = None,
        event_ttl_seconds: int | None = None,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._event_ttl_seconds = event_ttl_seconds

    async def get_session(self, ctx: SessionIdentity) -> SessionState:
        key = self._session_key(ctx)
        raw = await self._redis.get(key)
        if raw is None:
            raise SessionStateNotFoundError(f"session state not found: {key}")
        return SessionState.model_validate_json(_decode_json_blob(raw))

    async def set_session(
        self,
        state: SessionState,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        await self._redis.set(
            self._session_key(state),
            state.model_dump_json(),
            ex=self._resolve_ttl(ttl_seconds),
        )

    async def update_session(
        self,
        ctx: SessionIdentity,
        mutation: Mapping[str, object],
        *,
        expected_version: int | None = None,
    ) -> SessionState:
        return await self._update_json_model(
            key=self._session_key(ctx),
            model_type=SessionState,
            mutation=mutation,
            expected_version=expected_version,
            not_found_type=SessionStateNotFoundError,
        )

    async def append_workflow_event(
        self,
        ctx: SessionIdentity,
        event: WorkflowEventLike,
    ) -> None:
        workflow_id = event.workflow_id
        if workflow_id:
            key = build_workflow_events_key(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                workflow_id=workflow_id,
                prefix=self._key_prefix,
            )
        else:
            key = build_session_events_key(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                prefix=self._key_prefix,
            )

        await self._redis.rpush(key, event.model_dump_json(exclude_none=True))
        if self._event_ttl_seconds is not None:
            await self._redis.expire(key, self._event_ttl_seconds)

    async def get_workflow(
        self,
        ctx: SessionIdentity,
        workflow_id: str,
    ) -> WorkflowState:
        key = self._workflow_key(ctx, workflow_id)
        raw = await self._redis.get(key)
        if raw is None:
            raise WorkflowStateNotFoundError(f"workflow state not found: {key}")
        return WorkflowState.model_validate_json(_decode_json_blob(raw))

    async def set_workflow(
        self,
        state: WorkflowState,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        await self._redis.set(
            self._workflow_key(state, state.workflow_id),
            state.model_dump_json(),
            ex=self._resolve_ttl(ttl_seconds),
        )

    async def update_workflow(
        self,
        ctx: SessionIdentity,
        workflow_id: str,
        mutation: Mapping[str, object],
        *,
        expected_version: int | None = None,
    ) -> WorkflowState:
        return await self._update_json_model(
            key=self._workflow_key(ctx, workflow_id),
            model_type=WorkflowState,
            mutation=mutation,
            expected_version=expected_version,
            not_found_type=WorkflowStateNotFoundError,
        )

    async def _update_json_model(
        self,
        *,
        key: str,
        model_type: type[StateModelT],
        mutation: Mapping[str, object],
        expected_version: int | None,
        not_found_type: type[SessionStateStoreError],
    ) -> StateModelT:
        async with self._redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if raw is None:
                        raise not_found_type(f"state not found: {key}")

                    current = model_type.model_validate_json(_decode_json_blob(raw))
                    payload = current.model_dump()
                    current_version = payload.get("version")
                    if not isinstance(current_version, int):
                        raise SessionStateStoreError(f"state version is invalid: {key}")
                    if (
                        expected_version is not None
                        and current_version != expected_version
                    ):
                        raise SessionStateVersionConflictError(
                            f"expected version {expected_version}, found {current_version}"
                        )

                    payload.update(mutation)
                    payload["version"] = current_version + 1
                    payload["updated_at"] = datetime.now(UTC)
                    updated = model_type.model_validate(payload)

                    pipe.multi()
                    pipe.set(key, updated.model_dump_json(), ex=self._ttl_seconds)
                    await pipe.execute()
                    return updated
                except RedisWatchError:
                    await pipe.reset()

    def _resolve_ttl(self, ttl_seconds: int | None) -> int | None:
        return self._ttl_seconds if ttl_seconds is None else ttl_seconds

    def _session_key(self, ctx: SessionIdentity) -> str:
        return build_session_key(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            prefix=self._key_prefix,
        )

    def _workflow_key(self, ctx: SessionIdentity, workflow_id: str) -> str:
        return build_workflow_key(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            workflow_id=workflow_id,
            prefix=self._key_prefix,
        )
