from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from a2a_runtime.models import A2AEnvelope

RequestPayloadT = TypeVar("RequestPayloadT", bound=BaseModel)
ResponsePayloadT = TypeVar("ResponsePayloadT", bound=BaseModel)


class A2AServer(Protocol[RequestPayloadT, ResponsePayloadT]):
    """Inbound A2A dispatch boundary."""

    async def dispatch_envelope(
        self,
        envelope: A2AEnvelope[RequestPayloadT],
    ) -> A2AEnvelope[ResponsePayloadT]: ...
