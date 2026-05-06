from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SupervisorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subagent_db_path: Path = Field(default=Path("/data/supervisor/subagents.sqlite"))
    observability_sidecar_url: str | None = None
    auth0_domain: str | None = None
    auth0_audience: str | None = None
    auth0_management_client_id: str | None = None
    auth0_management_client_secret: str | None = None
    auth0_management_audience: str | None = None

    @classmethod
    def from_env(cls) -> SupervisorSettings:
        return cls(
            subagent_db_path=Path(
                os.getenv("SUBAGENT_DB_PATH", "/data/supervisor/subagents.sqlite")
            ),
            observability_sidecar_url=os.getenv("OBSERVABILITY_SIDECAR_URL"),
            auth0_domain=os.getenv("AUTH0_DOMAIN"),
            auth0_audience=os.getenv("AUTH0_AUDIENCE"),
            auth0_management_client_id=os.getenv("AUTH0_MANAGEMENT_CLIENT_ID"),
            auth0_management_client_secret=os.getenv("AUTH0_MANAGEMENT_CLIENT_SECRET"),
            auth0_management_audience=os.getenv("AUTH0_MANAGEMENT_AUDIENCE"),
        )
