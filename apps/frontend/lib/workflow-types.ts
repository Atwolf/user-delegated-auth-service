export type WorkflowStatus =
  | "created"
  | "planned"
  | "ready"
  | "awaiting_approval"
  | "approved"
  | "executing"
  | "completed"
  | "failed"
  | "cancelled";

export type WorkflowStep = {
  step_id: string;
  target_agent: string;
  action: string;
  input_model_type: string;
  input_payload_json: string;
  required_scopes: string[];
  downstream_audience?: string | null;
  operation_type?: "READ" | "WRITE" | "ADMIN";
  blast_radius?: string | null;
  hitl_description?: string | null;
  mutates_external_state: boolean;
};

export type WorkflowProposal = {
  agent_name: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  reason?: string | null;
};

export type AuthorizationBundle = {
  workflow_id: string;
  scopes: string[];
  proposals: WorkflowProposal[];
};

export type WorkflowTimelineEvent = {
  event_type: string;
  message: string;
  step_id?: string | null;
  attributes: Record<string, unknown>;
  created_at: string;
};

export type WorkflowRecord = {
  workflow_id: string;
  status: { status: WorkflowStatus };
  plan_hash: string;
  token_exchange?: {
    attempted: boolean;
    audience?: string | null;
    scopes: string[];
    expires_at?: string | null;
  };
  authorization: AuthorizationBundle;
  plan: {
    workflow_id: string;
    user_id: string;
    session_id: string;
    tenant_id?: string | null;
    created_at: string;
    steps: WorkflowStep[];
  };
  events: WorkflowTimelineEvent[];
  step_results: Array<{
    step_id: string;
    target_agent: string;
    action: string;
    status: "completed" | "failed";
    output: Record<string, unknown>;
  }>;
};
