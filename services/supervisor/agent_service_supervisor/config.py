from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict


class SupervisorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observability_sidecar_url: str | None = None
    auth0_domain: str | None = None
    auth0_audience: str | None = None
    auth0_management_client_id: str | None = None
    auth0_management_client_secret: str | None = None
    auth0_management_audience: str | None = None
    internal_service_auth_secret: str | None = None

    @classmethod
    def from_env(cls) -> SupervisorSettings:
        return cls(
            observability_sidecar_url=os.getenv("OBSERVABILITY_SIDECAR_URL"),
            auth0_domain=os.getenv("AUTH0_DOMAIN"),
            auth0_audience=os.getenv("AUTH0_AUDIENCE"),
            auth0_management_client_id=os.getenv("AUTH0_MANAGEMENT_CLIENT_ID"),
            auth0_management_client_secret=os.getenv("AUTH0_MANAGEMENT_CLIENT_SECRET"),
            auth0_management_audience=os.getenv("AUTH0_MANAGEMENT_AUDIENCE"),
            internal_service_auth_secret=os.getenv("INTERNAL_SERVICE_AUTH_SECRET"),
        )
