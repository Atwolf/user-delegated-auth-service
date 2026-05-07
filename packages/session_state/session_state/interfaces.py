from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .models import SessionState, WorkflowState


class SessionIdentity(Protocol):
    tenant_id: str | None
    user_id: str
    session_id: str


class WorkflowEventLike(Protocol):
    workflow_id: str | None

    def model_dump_json(self, **kwargs: object) -> str: ...


class SessionStateStore(Protocol):
    async def get_session(self, ctx: SessionIdentity) -> SessionState: ...

    async def set_session(
        self,
        state: SessionState,
        *,
        ttl_seconds: int | None = None,
    ) -> None: ...

    async def update_session(
        self,
        ctx: SessionIdentity,
        mutation: Mapping[str, object],
        *,
        expected_version: int | None = None,
    ) -> SessionState: ...

    async def append_workflow_event(
        self,
        ctx: SessionIdentity,
        event: WorkflowEventLike,
    ) -> None: ...

    async def get_workflow(
        self,
        ctx: SessionIdentity,
        workflow_id: str,
    ) -> WorkflowState: ...

    async def set_workflow(
        self,
        state: WorkflowState,
        *,
        ttl_seconds: int | None = None,
    ) -> None: ...

    async def update_workflow(
        self,
        ctx: SessionIdentity,
        workflow_id: str,
        mutation: Mapping[str, object],
        *,
        expected_version: int | None = None,
    ) -> WorkflowState: ...
