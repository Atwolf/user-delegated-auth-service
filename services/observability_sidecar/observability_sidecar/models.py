from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from observability.models import WorkflowEvent
from observability.redaction import redact_sensitive
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgenticTraceIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_component: str = Field(..., min_length=1)
    event: WorkflowEvent


class LogIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_component: str = Field(..., min_length=1)
    level: Literal["debug", "info", "warning", "error", "critical"]
    message: str = Field(..., min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    agentic_span_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    def redacted(self) -> LogIngest:
        return self.model_copy(
            update={
                "attributes": redact_sensitive(self.attributes),
                "message": redact_sensitive(self.message),
            }
        )


class SidecarStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_count: int = Field(ge=0)
    log_count: int = Field(ge=0)


class TelemetrySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traces: list[AgenticTraceIngest] = Field(default_factory=list[AgenticTraceIngest])
    logs: list[LogIngest] = Field(default_factory=list[LogIngest])
    stats: SidecarStats
