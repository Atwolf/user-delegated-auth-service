from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AgentRuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
