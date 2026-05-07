from __future__ import annotations

from threading import Lock

from .models import PlanWorkflowRequest, SessionRecord, WorkflowRecord, utc_now


class InMemoryStateStore:
    """Process-local POC store for session and workflow proposal records."""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], SessionRecord] = {}
        self._workflows: dict[str, WorkflowRecord] = {}
        self._lock = Lock()

    def upsert_session(self, request: PlanWorkflowRequest) -> SessionRecord:
        record = SessionRecord(
            user_id=request.user_id,
            session_id=request.session_id,
            token_ref=request.token_ref,
            auth_context_ref=request.auth_context_ref,
            token_scopes=request.token_scopes,
            allowed_tools=request.allowed_tools,
            tenant_id=request.tenant_id,
            updated_at=utc_now(),
        )
        with self._lock:
            self._sessions[(request.user_id, request.session_id)] = record
        return record

    def save_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        with self._lock:
            self._workflows[record.workflow_id] = record
        return record

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        with self._lock:
            return self._workflows.get(workflow_id)
