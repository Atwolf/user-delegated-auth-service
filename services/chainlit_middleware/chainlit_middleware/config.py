from __future__ import annotations

import os

from pydantic import BaseModel, Field


class ChainlitMiddlewareSettings(BaseModel):
    ag_ui_gateway_url: str = Field(default="http://ag-ui-gateway:8088/agent")
    agent_service_url: str = Field(default="http://agent-service:8090")
    request_timeout_seconds: float = Field(default=10.0, gt=0)

    @classmethod
    def from_env(cls) -> ChainlitMiddlewareSettings:
        return cls(
            ag_ui_gateway_url=os.getenv(
                "AG_UI_GATEWAY_URL",
                "http://ag-ui-gateway:8088/agent",
            ),
            agent_service_url=os.getenv("AGENT_SERVICE_URL", "http://agent-service:8090"),
            request_timeout_seconds=float(os.getenv("AG_UI_REQUEST_TIMEOUT_SECONDS", "10")),
        )
