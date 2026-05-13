from __future__ import annotations

from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata, utc_now_iso
from adk_agent_service.stores.thread_metadata import (
    DEFAULT_KEY_PREFIX,
    thread_metadata_key,
)


class InMemoryThreadMetadataStore:
    def __init__(self, *, key_prefix: str = DEFAULT_KEY_PREFIX) -> None:
        self._key_prefix = key_prefix
        self._entries: dict[str, ThreadRunMetadata] = {}

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
        self._entries[key] = metadata
        return key, metadata
