from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel

from agent_runtime.context import AgentInvocationContext

if TYPE_CHECKING:
    from a2a_runtime.models import A2AEnvelope

RequestPayloadT = TypeVar("RequestPayloadT", bound=BaseModel)
ResponsePayloadT = TypeVar("ResponsePayloadT", bound=BaseModel)


class AgentHandler(Protocol[RequestPayloadT, ResponsePayloadT]):
    """Agent boundary invoked after A2A envelope validation."""

    async def handle(
        self,
        ctx: AgentInvocationContext,
        envelope: A2AEnvelope[RequestPayloadT],
    ) -> A2AEnvelope[ResponsePayloadT]: ...
