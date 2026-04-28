from __future__ import annotations

from workflow_core import ToolProposal

from planner_agent.app import CapabilityRequest, CapabilityResponse


class PlannerHandler:
    async def propose(self, request: CapabilityRequest) -> CapabilityResponse:
        return CapabilityResponse(
            proposals=[
                ToolProposal(
                    agent_name="planner",
                    tool_name="propose_workflow_plan",
                    arguments={"query": request.query},
                    reason="Planner scaffold",
                )
            ]
        )
