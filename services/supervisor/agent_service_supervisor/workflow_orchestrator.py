from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field
from workflow_core.models import AuthorizationBundle, ToolProposal

from agent_service_supervisor.discovery_sqlite import (
    SubagentDiscoveryService,
    SubagentRecord,
)


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)


class CapabilityProposalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: list[ToolProposal] = Field(default_factory=list[ToolProposal])


class WorkflowOrchestrator:
    """Skeleton for supervisor plan-authorize-execute orchestration."""

    def __init__(
        self,
        discovery: SubagentDiscoveryService,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._discovery = discovery
        self._http_client = http_client
        self._timeout = timeout

    async def discover_subagents(self) -> list[SubagentRecord]:
        return await self._discovery.load_enabled_subagents()

    async def request_tool_proposals(
        self,
        *,
        user_query: str,
        user_id: str,
        session_id: str,
        subagents: Sequence[SubagentRecord] | None = None,
    ) -> list[ToolProposal]:
        """Request proposal contracts from active subagents."""

        resolved_subagents = (
            list(subagents) if subagents is not None else await self.discover_subagents()
        )
        request = CapabilityRequest(
            query=user_query,
            user_id=user_id,
            session_id=session_id,
        )

        proposals: list[ToolProposal] = []
        for subagent in resolved_subagents:
            subagent_proposals = await self._request_single_subagent(subagent, request)
            proposals.extend(subagent_proposals)

        return proposals

    def build_authorization_bundle(
        self,
        *,
        workflow_id: str,
        proposals: Sequence[ToolProposal],
        scopes: Sequence[str],
    ) -> AuthorizationBundle:
        typed_proposals = [ToolProposal.model_validate(proposal) for proposal in proposals]
        return AuthorizationBundle(
            workflow_id=workflow_id,
            scopes=sorted(set(scopes)),
            proposals=typed_proposals,
        )

    async def _request_single_subagent(
        self,
        subagent: SubagentRecord,
        request: CapabilityRequest,
    ) -> list[ToolProposal]:
        endpoint = f"{subagent.base_url.rstrip('/')}/capabilities"
        try:
            response = await self._post(endpoint, request)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError):
            return []

        payload = cast(dict[str, Any], response.json())
        return _parse_capability_payload(payload, default_agent_name=subagent.agent_name)

    async def _post(
        self,
        endpoint: str,
        request: CapabilityRequest,
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(
                endpoint,
                json=request.model_dump(mode="json"),
            )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(endpoint, json=request.model_dump(mode="json"))


def _parse_capability_payload(
    payload: dict[str, Any],
    *,
    default_agent_name: str,
) -> list[ToolProposal]:
    if "proposals" in payload:
        batch = CapabilityProposalBatch.model_validate(payload)
        return batch.proposals

    legacy_payload = dict(payload)
    legacy_payload.setdefault("agent_name", default_agent_name)
    return [ToolProposal.model_validate(legacy_payload)]
