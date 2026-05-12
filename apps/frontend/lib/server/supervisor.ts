import {
  parseScopeString,
  type Auth0ServerSession,
  type Auth0UserSession
} from "@/lib/auth0-config";
import { signedSessionContextHeaders } from "@/lib/server/internal-auth";
import { sanitizeBrowserRecord, sanitizeBrowserValue } from "@/lib/server/redaction";

type UserSessionMetadataInput = {
  audience: string | null;
  expiresAt: number | null;
  sessionId: string;
  tenantId?: string | null;
  tokenRef: string;
  tokenScopes: string[];
  userEmail: string | null;
  userId: string;
  userName: string | null;
};

export type SanitizedSessionContext = {
  allowed_tools: string[];
  session_id: string;
  token_ref: string;
  token_scopes: string[];
  tenant_id?: string;
  user_id: string;
};

export type AgentThreadSnapshot = {
  messages: unknown[];
  state: Record<string, unknown>;
  threadId: string;
  title: string | null;
};

export type WorkflowApprovalSnapshot = {
  workflow: Record<string, unknown>;
};

export type WorkflowSnapshot = {
  workflow: Record<string, unknown>;
};

const supervisorBaseUrl = () =>
  (process.env.SUPERVISOR_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

const agentServiceBaseUrl = () =>
  (process.env.AGENT_SERVICE_URL ?? "http://127.0.0.1:8090").replace(/\/+$/, "");

async function postSupervisor<TResponse>(
  path: string,
  body: Record<string, unknown>,
  failureMessage: string,
  sessionContext?: SanitizedSessionContext
): Promise<TResponse> {
  const correlationId = crypto.randomUUID();
  const response = await fetch(`${supervisorBaseUrl()}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(sessionContext ? signedSessionContextHeaders(sessionContext, correlationId) : {})
    },
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
  failureMessage: string,
  sessionContext?: SanitizedSessionContext
): Promise<TResponse> {
  const correlationId = crypto.randomUUID();
  const response = await fetch(`${agentServiceBaseUrl()}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(sessionContext ? signedSessionContextHeaders(sessionContext, correlationId) : {})
    },
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

async function getAgentService<TResponse>(
  path: string,
  query: Record<string, string | null | undefined>,
  failureMessage: string,
  sessionContext?: SanitizedSessionContext
): Promise<TResponse> {
  const url = new URL(`${agentServiceBaseUrl()}${path}`);
  for (const [key, value] of Object.entries(query)) {
    if (value) url.searchParams.set(key, value);
  }
  const response = await fetch(url.toString(), {
    method: "GET",
    cache: "no-store",
    headers: sessionContext ? signedSessionContextHeaders(sessionContext, crypto.randomUUID()) : {}
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
  const sessionContext: SanitizedSessionContext = {
    allowed_tools: [],
    session_id: input.sessionId,
    token_ref: input.tokenRef,
    token_scopes: input.tokenScopes,
    user_id: input.userId
  };
  if (input.tenantId) sessionContext.tenant_id = input.tenantId;
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
      tenant_id: input.tenantId ?? null,
      user_email: input.userEmail,
      user_id: input.userId,
      user_name: input.userName
    },
    "Auth0 session metadata loading failed",
    sessionContext
  );

  return {
    audience: result.audience,
    expiresAt: input.expiresAt,
    sessionId: input.sessionId,
    tenantId: input.tenantId ?? null,
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

export function sanitizedSessionContext(session: Auth0UserSession): SanitizedSessionContext {
  const context: SanitizedSessionContext = {
    allowed_tools: [...new Set(session.allowedTools)].sort(),
    session_id: session.sessionId,
    token_ref: session.tokenRef,
    token_scopes: parseScopeString(session.scope),
    user_id: session.userId
  };
  if (session.tenantId) context.tenant_id = session.tenantId;
  return context;
}

export async function createAgentThread(
  session: Auth0UserSession,
  input: { title?: string | null } = {}
): Promise<AgentThreadSnapshot> {
  const context = sanitizedSessionContext(session);
  const response = await postAgentService<AgentThreadResponse>(
    "/threads",
    {
      allowed_tools: context.allowed_tools,
      session_id: context.session_id,
      state: {},
      title: input.title ?? null,
      token_ref: context.token_ref,
      token_scopes: context.token_scopes,
      user_id: context.user_id
    },
    "Thread creation failed",
    context
  );
  return normalizeAgentThread(response);
}

export async function registerAgentAuthContext(session: Auth0ServerSession): Promise<void> {
  const context = sanitizedSessionContext(session);
  await postAgentService<{ token_ref: string }>(
    "/token-context",
    {
      auth_context_ref: session.authContextRef,
      token_ref: context.token_ref
    },
    "Auth token registration failed",
    context
  );
}

export async function restoreAgentThread(
  threadId: string,
  session: Auth0UserSession
): Promise<AgentThreadSnapshot> {
  const context = sanitizedSessionContext(session);
  const response = await getAgentService<AgentThreadResponse>(
    `/threads/${encodeURIComponent(threadId)}`,
    {},
    "Thread restore failed",
    context
  );
  return normalizeAgentThread(response, threadId);
}

export async function restoreAgentWorkflow(
  workflowId: string,
  session: Auth0UserSession
): Promise<WorkflowSnapshot> {
  const context = sanitizedSessionContext(session);
  const response = await getAgentService<WorkflowResponse>(
    `/workflows/${encodeURIComponent(workflowId)}`,
    {},
    "Workflow restore failed",
    context
  );
  return { workflow: normalizeWorkflow(response) };
}

export async function approveAgentWorkflow(
  workflowId: string,
  session: Auth0UserSession,
  input: { approved: boolean; planHash: string }
): Promise<WorkflowApprovalSnapshot> {
  const context = sanitizedSessionContext(session);
  const response = await postAgentService<WorkflowApprovalResponse>(
    `/workflows/${encodeURIComponent(workflowId)}/approve`,
    {
      approved: input.approved,
      plan_hash: input.planHash
    },
    "Workflow approval failed",
    context
  );
  return normalizeWorkflowApproval(response);
}

type AgentThreadResponse = {
  thread?: AgentThreadResponse;
  messages?: unknown;
  state?: unknown;
  thread_id?: unknown;
  threadId?: unknown;
  title?: unknown;
};

type WorkflowApprovalResponse = {
  workflow?: unknown;
};

type WorkflowResponse = {
  workflow?: unknown;
};

function normalizeAgentThread(
  response: AgentThreadResponse,
  fallbackThreadId?: string
): AgentThreadSnapshot {
  const payload = response.thread ?? response;
  const threadId =
    typeof payload.threadId === "string"
      ? payload.threadId
      : typeof payload.thread_id === "string"
        ? payload.thread_id
        : fallbackThreadId;

  if (!threadId) {
    throw new Error("Agent Service returned a thread response without a thread id");
  }

  return {
    messages: sanitizeThreadMessages(payload.messages),
    state: isRecord(payload.state) ? sanitizeBrowserRecord(payload.state) : {},
    threadId,
    title: typeof payload.title === "string" ? payload.title : null
  };
}

function normalizeWorkflowApproval(response: WorkflowApprovalResponse): WorkflowApprovalSnapshot {
  return {
    workflow: normalizeWorkflow(response)
  };
}

function normalizeWorkflow(response: WorkflowResponse): Record<string, unknown> {
  if (!isRecord(response.workflow)) {
    throw new Error("Agent Service returned a response without a workflow");
  }
  return sanitizeBrowserRecord(response.workflow);
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

const RESTORABLE_MESSAGE_ROLES = new Set(["assistant", "system", "user"]);

function sanitizeThreadMessages(value: unknown): unknown[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((message) => sanitizeBrowserValue(message))
    .filter((message) => {
      if (!isRecord(message)) return false;
      const role = message.role;
      return typeof role === "string" && RESTORABLE_MESSAGE_ROLES.has(role);
    }) as unknown[];
}
