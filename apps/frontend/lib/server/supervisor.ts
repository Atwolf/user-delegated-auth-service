import { parseScopeString, type Auth0UserSession } from "@/lib/auth0-config";
import type { WorkflowRecord } from "@/lib/workflow-types";

type UserSessionMetadataInput = {
  audience: string | null;
  expiresAt: number | null;
  sessionId: string;
  tokenRef: string;
  tokenScopes: string[];
  userEmail: string | null;
  userId: string;
  userName: string | null;
};

const supervisorBaseUrl = () =>
  (process.env.SUPERVISOR_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

const agentServiceBaseUrl = () =>
  (process.env.AGENT_SERVICE_URL ?? "http://127.0.0.1:8090").replace(/\/+$/, "");

async function postSupervisor<TResponse>(
  path: string,
  body: Record<string, unknown>,
  failureMessage: string
): Promise<TResponse> {
  const response = await fetch(`${supervisorBaseUrl()}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store"
  });

  if (!response.ok) {
    const detail = await responseErrorDetail(response);
    throw new Error(
      `${failureMessage} with HTTP ${response.status}${detail ? `: ${detail}` : ""}`
    );
  }

  return (await response.json()) as TResponse;
}

async function postAgentService<TResponse>(
  path: string,
  body: Record<string, unknown>,
  failureMessage: string
): Promise<TResponse> {
  const response = await fetch(`${agentServiceBaseUrl()}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store"
  });

  if (!response.ok) {
    const detail = await responseErrorDetail(response);
    throw new Error(
      `${failureMessage} with HTTP ${response.status}${detail ? `: ${detail}` : ""}`
    );
  }

  return (await response.json()) as TResponse;
}

export async function loadAuth0UserSession(
  input: UserSessionMetadataInput
): Promise<Auth0UserSession> {
  const result = await postSupervisor<{
    scope: string;
    audience: string | null;
    token_ref: string;
    user_id: string;
    user_email: string | null;
    allowed_tools: string[];
    persona: {
      display_name: string;
      headline: string;
      greeting: string;
      traits: string[];
    };
  }>(
    "/identity/auth0/session",
    {
      audience: input.audience,
      session_id: input.sessionId,
      token_ref: input.tokenRef,
      token_scopes: input.tokenScopes,
      user_email: input.userEmail,
      user_id: input.userId,
      user_name: input.userName
    },
    "Auth0 session metadata loading failed"
  );

  return {
    audience: result.audience,
    expiresAt: input.expiresAt,
    sessionId: input.sessionId,
    tokenRef: result.token_ref,
    scope: result.scope,
    userId: result.user_id,
    userEmail: result.user_email,
    allowedTools: result.allowed_tools,
    persona: {
      displayName: result.persona.display_name,
      headline: result.persona.headline,
      greeting: result.persona.greeting,
      traits: result.persona.traits
    }
  };
}

export async function planWorkflow(
  question: string,
  session: Auth0UserSession
): Promise<WorkflowRecord> {
  const response = await postAgentService<AgentWorkflowResponse | WorkflowRecord>(
    "/workflows/plan",
    {
      question,
      auth_context_ref: session.authContextRef,
      user_id: session.userId,
      session_id: session.sessionId,
      token_ref: session.tokenRef,
      token_scopes: parseScopeString(session.scope),
      allowed_tools: [...new Set(session.allowedTools)].sort()
    },
    "Workflow planning failed"
  );
  return normalizeWorkflowResponse(response);
}

export async function approveWorkflow(
  workflowId: string,
  planHash: string,
  session: Auth0UserSession
): Promise<WorkflowRecord> {
  const response = await postAgentService<AgentWorkflowResponse | WorkflowRecord>(
    `/workflows/${workflowId}/approve`,
    {
      approved: true,
      approved_by_user_id: session.userId,
      plan_hash: planHash
    },
    "Workflow approval failed"
  );
  return normalizeWorkflowResponse(response);
}

type AgentWorkflowRecord = {
  workflow_id: string;
  status: WorkflowRecord["status"]["status"];
  proposal: WorkflowRecord["plan"];
  plan_hash: string;
  tool_intents: Array<{
    agent_name: string;
    tool_name: string;
    arguments: Record<string, unknown>;
    reason?: string | null;
  }>;
  policy: {
    required_scopes: string[];
  };
  egress_results?: Array<Record<string, unknown>>;
  created_at: string;
};

type AgentWorkflowResponse = {
  workflow?: AgentWorkflowRecord;
  token_exchange?: WorkflowRecord["token_exchange"];
};

function toWorkflowRecord(
  workflow: AgentWorkflowRecord,
  tokenExchange?: WorkflowRecord["token_exchange"]
): WorkflowRecord {
  return {
    workflow_id: workflow.workflow_id,
    status: { status: workflow.status },
    plan_hash: workflow.plan_hash,
    token_exchange: tokenExchange,
    authorization: {
      workflow_id: workflow.workflow_id,
      scopes: workflow.policy.required_scopes,
      proposals: workflow.tool_intents.map((intent) => ({
        agent_name: intent.agent_name,
        tool_name: intent.tool_name,
        arguments: intent.arguments,
        reason: intent.reason ?? null
      }))
    },
    plan: workflow.proposal,
    events: [
      {
        event_type: "agent_service.workflow_planned",
        message: "Agent Service returned a deterministic workflow manifest.",
        attributes: {},
        created_at: workflow.created_at
      },
      ...(tokenExchange?.attempted
        ? [
            {
              event_type: "agent_service.obo_token_exchange",
              message:
                "Agent Service attempted an approval-bound Auth0 OBO token exchange.",
              attributes: {
                audience: tokenExchange.audience ?? null,
                expires_at: tokenExchange.expires_at ?? null,
                scopes: tokenExchange.scopes
              },
              created_at: new Date().toISOString()
            }
          ]
        : [])
    ],
    step_results: (workflow.egress_results ?? []).map((result, index) => ({
      step_id: `step-${index + 1}`,
      target_agent: String(result.target_mcp ?? "egress_gateway"),
      action: String(result.tool_name ?? "egress"),
      status: "completed",
      output: result
    }))
  };
}

function normalizeWorkflowResponse(
  response: AgentWorkflowResponse | WorkflowRecord
): WorkflowRecord {
  if ("workflow" in response && response.workflow) {
    return toWorkflowRecord(response.workflow, response.token_exchange);
  }
  return response as WorkflowRecord;
}

async function responseErrorDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as unknown;
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as { detail?: unknown }).detail;
      return typeof detail === "string" ? detail : "";
    }
  } catch {
    return "";
  }
  return "";
}
