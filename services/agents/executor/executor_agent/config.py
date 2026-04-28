from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExecutorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = "executor"
