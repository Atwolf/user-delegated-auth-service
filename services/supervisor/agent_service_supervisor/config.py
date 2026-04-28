from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SupervisorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subagent_db_path: Path = Field(default=Path("/data/supervisor/subagents.sqlite"))
    observability_sidecar_url: str | None = None
    auth0_client_secret: str | None = None

    @classmethod
    def from_env(cls) -> SupervisorSettings:
        return cls(
            subagent_db_path=Path(
                os.getenv("SUBAGENT_DB_PATH", "/data/supervisor/subagents.sqlite")
            ),
            observability_sidecar_url=os.getenv("OBSERVABILITY_SIDECAR_URL"),
            auth0_client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
        )
