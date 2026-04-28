import type { Auth0Config } from "@/lib/auth0-config";
import type { WorkflowRecord } from "@/lib/workflow-types";

export type TokenExchangeResult = {
  access_token: string;
  token_type: "Bearer";
  expires_in: number | null;
  scope: string;
  audience: string | null;
  token_ref: string;
};

const supervisorBaseUrl = () =>
  (process.env.SUPERVISOR_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

const isMockSupervisor = () => process.env.SUPERVISOR_BASE_URL === "mock";

export async function exchangeClientCredentials(
  config: Auth0Config
): Promise<TokenExchangeResult> {
  if (isMockSupervisor()) {
    return {
      access_token: "mock-access-token",
      token_type: "Bearer",
      expires_in: 3600,
      scope: config.scope,
      audience: config.audience || null,
      token_ref: "auth0:mock"
    };
  }

  const response = await fetch(`${supervisorBaseUrl()}/identity/client-credentials/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      domain: config.domain,
      token_endpoint: config.tokenEndpoint,
      jwks_endpoint: config.jwksEndpoint,
      client_id: config.clientId,
      client_secret: config.clientSecret,
      scope: config.scope,
      audience: config.audience || null,
      user_id: "sample-user",
      session_id: "sample-session"
    }),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Token exchange failed with HTTP ${response.status}`);
  }

  return (await response.json()) as TokenExchangeResult;
}

export async function planWorkflow(
  question: string,
  tokenRef: string
): Promise<WorkflowRecord> {
  if (isMockSupervisor()) {
    return mockWorkflow(question, tokenRef, "awaiting_approval");
  }

  const response = await fetch(`${supervisorBaseUrl()}/workflows/plan`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      question,
      user_id: "sample-user",
      session_id: "sample-session",
      token_ref: tokenRef
    }),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Workflow planning failed with HTTP ${response.status}`);
  }

  return (await response.json()) as WorkflowRecord;
}

export async function approveWorkflow(
  workflowId: string,
  planHash: string,
  tokenRef?: string | null
): Promise<WorkflowRecord> {
  if (isMockSupervisor()) {
    return {
      ...mockWorkflow("approved mock workflow", tokenRef ?? "auth0:mock", "completed"),
      workflow_id: workflowId,
      plan_hash: planHash
    };
  }

  const response = await fetch(`${supervisorBaseUrl()}/workflows/${workflowId}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      approved: true,
      approved_by_user_id: "sample-user",
      plan_hash: planHash,
      token_ref: tokenRef ?? null
    }),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Workflow approval failed with HTTP ${response.status}`);
  }

  return (await response.json()) as WorkflowRecord;
}

function mockWorkflow(
  question: string,
  tokenRef: string,
  status: WorkflowRecord["status"]["status"]
): WorkflowRecord {
  const now = new Date().toISOString();
  const steps = [
    {
      step_id: "step-001",
      target_agent: "planner",
      action: "propose_workflow_plan",
      input_model_type: "propose_workflow_plan.arguments",
      input_payload_json: JSON.stringify({ query: question }),
      required_scopes: ["DOE.Workflow.plan"],
      downstream_audience: null,
      mutates_external_state: false
    },
    {
      step_id: "step-002",
      target_agent: "identity",
      action: "get_identity_profile",
      input_model_type: "get_identity_profile.arguments",
      input_payload_json: JSON.stringify({ subject_user_id: "sample-user" }),
      required_scopes: ["DOE.Identity.sample-user"],
      downstream_audience: null,
      mutates_external_state: false
    },
    {
      step_id: "step-003",
      target_agent: "developer",
      action: "get_developer_app",
      input_model_type: "get_developer_app.arguments",
      input_payload_json: JSON.stringify({ appid: "sample-app" }),
      required_scopes: ["DOE.Developer.sample-app"],
      downstream_audience: null,
      mutates_external_state: false
    }
  ];

  return {
    workflow_id: "wf-mock",
    status: { status },
    plan_hash: "sha256:mock",
    authorization: {
      workflow_id: "wf-mock",
      scopes: [
        "DOE.Developer.sample-app",
        "DOE.Identity.sample-user",
        "DOE.Workflow.plan"
      ],
      proposals: []
    },
    plan: {
      workflow_id: "wf-mock",
      user_id: "sample-user",
      session_id: "sample-session",
      created_at: now,
      steps
    },
    events: [
      {
        event_type: "workflow.planned",
        message: "Mock workflow planned.",
        attributes: { token_ref: tokenRef },
        created_at: now
      },
      {
        event_type: status === "completed" ? "workflow.completed" : "workflow.awaiting_approval",
        message: status === "completed" ? "Mock workflow completed." : "Mock workflow awaiting approval.",
        attributes: {},
        created_at: now
      }
    ],
    step_results:
      status === "completed"
        ? steps.map((step) => ({
            step_id: step.step_id,
            target_agent: step.target_agent,
            action: step.action,
            status: "completed" as const,
            output: { deterministic: true }
          }))
        : []
  };
}
