from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from a2a_runtime.models import A2AEnvelope

RequestPayloadT = TypeVar("RequestPayloadT", bound=BaseModel)
ResponsePayloadT = TypeVar("ResponsePayloadT", bound=BaseModel)


class A2AClient(Protocol[RequestPayloadT, ResponsePayloadT]):
    """Outbound A2A transport boundary."""

    async def send_envelope(
        self,
        envelope: A2AEnvelope[RequestPayloadT],
    ) -> A2AEnvelope[ResponsePayloadT]: ...
