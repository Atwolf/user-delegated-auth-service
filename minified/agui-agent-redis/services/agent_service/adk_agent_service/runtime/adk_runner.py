from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from ag_ui.core import BaseEvent, EventType, RunAgentInput

from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata
from adk_agent_service.runtime.agent import APP_NAME, build_root_agent
from adk_agent_service.runtime.agui_mapper import (
    event_type,
    thread_metadata_delta,
    to_agui_input,
    user_id_from_agui_input,
)


class AdkBridge(Protocol):
    def run(self, input_data: RunAgentInput) -> AsyncIterator[BaseEvent]: ...


async def stream_adk_events(
    request: AgentRunRequest,
    metadata_key: str,
    metadata: ThreadRunMetadata,
) -> AsyncIterator[BaseEvent]:
    metadata_delta_sent = False
    async for event in build_adk_bridge().run(to_agui_input(request, metadata)):
        yield event
        if not metadata_delta_sent and event_type(event) == EventType.RUN_STARTED.value:
            yield thread_metadata_delta(metadata_key, metadata)
            metadata_delta_sent = True


def build_adk_bridge() -> AdkBridge:
    try:
        from ag_ui_adk import ADKAgent
    except ImportError as exc:
        raise RuntimeError("ag_ui_adk is required") from exc

    return ADKAgent(
        adk_agent=build_root_agent(),
        app_name=APP_NAME,
        user_id_extractor=user_id_from_agui_input,
        use_in_memory_services=True,
        use_thread_id_as_session_id=True,
        capabilities={
            "transport": {"streaming": True},
            "state": {"shared": True},
            "custom": {"redisThreadMetadata": True},
        },
    )
