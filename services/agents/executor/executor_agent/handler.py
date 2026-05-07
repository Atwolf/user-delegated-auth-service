from __future__ import annotations

from executor_agent.app import ExecuteStepRequest, ExecuteStepResponse


class ExecutorHandler:
    async def execute(self, request: ExecuteStepRequest) -> ExecuteStepResponse:
        return ExecuteStepResponse(
            workflow_id=request.workflow_id,
            step_id=request.step_id,
            result={"action": request.action, "arguments": request.arguments},
        )
