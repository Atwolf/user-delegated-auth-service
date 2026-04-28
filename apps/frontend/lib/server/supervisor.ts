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

export async function exchangeClientCredentials(
  config: Auth0Config
): Promise<TokenExchangeResult> {
  return postSupervisor<TokenExchangeResult>(
    "/identity/client-credentials/token",
    {
      domain: config.domain,
      token_endpoint: config.tokenEndpoint,
      jwks_endpoint: config.jwksEndpoint,
      client_id: config.clientId,
      client_secret: config.clientSecret,
      scope: config.scope,
      audience: config.audience || null,
      user_id: "sample-user",
      session_id: "sample-session"
    },
    "Token exchange failed"
  );
}

export async function planWorkflow(
  question: string,
  tokenRef: string,
  tokenScope: string
): Promise<WorkflowRecord> {
  return postSupervisor<WorkflowRecord>(
    "/workflows/plan",
    {
      question,
      user_id: "sample-user",
      session_id: "sample-session",
      token_ref: tokenRef,
      token_scopes: parseScopes(tokenScope)
    },
    "Workflow planning failed"
  );
}

export async function approveWorkflow(
  workflowId: string,
  planHash: string,
  tokenRef?: string | null
): Promise<WorkflowRecord> {
  return postSupervisor<WorkflowRecord>(
    `/workflows/${workflowId}/approve`,
    {
      approved: true,
      approved_by_user_id: "sample-user",
      plan_hash: planHash,
      token_ref: tokenRef ?? null
    },
    "Workflow approval failed"
  );
}

function parseScopes(scope: string): string[] {
  return [...new Set(scope.split(/\s+/).map((item) => item.trim()).filter(Boolean))].sort();
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
