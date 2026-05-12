# Agent Service Architecture

The service is organized around a narrower set of Pydantic v2 contracts:

- `workflow_core` owns workflow plans, steps, authorization bundles, scope materialization, and
  stable plan hashing. It also owns the `ToolIntent`, `WorkflowPolicyDecision`, and
  `EgressRequest` contracts used between the AG-UI gateway, agent service, egress gateway, and
  MCP services.
- `mcp_runtime` owns the FastMCP integration surface used by MCP services: direct FastMCP
  imports, Auth0-compatible runtime scope checks, and workflow authorization decorators.
- `session_state` owns Redis-backed session, workflow, and AG-UI thread state contracts.
- `token_broker` owns OBO token exchange request/response contracts.
- `observability` owns redaction-safe event emission helpers.
- `observability_sidecar` receives agentic traces and log payloads over HTTP, redacts
  sensitive fields, and exposes bounded recent telemetry for tests and local monitoring.
- `apps/frontend` is a standalone Next.js assistant-ui sample. It owns the browser Auth0
  session routes, assistant-ui AG-UI runtime wiring, MUI drawer surface, and authenticated
  browser proxies into the AG-UI and Agent Service boundaries.
- `ag_ui_gateway` exposes the `/agent` HTTP/SSE boundary and forwards AG-UI run input to
  Agent Service `/runs/stream`. It re-encodes the Agent Runtime event stream as AG-UI SSE.
- `agent_service` is the Coordinator/Dispatcher runtime boundary. The active run path
  reaches a Google ADK coordinator agent, using the configured Claude model through ADK's
  Anthropic adapter when `ANTHROPIC_API_KEY` is present. Redis-backed state is required for
  the reference runtime; in-memory state is reserved for explicitly injected tests. It now owns workflow
  planning, thread state, approval validation, server-side token-context lookup, OBO exchange,
  and egress delegation.
- `egress_gateway` is the only modeled outbound MCP/HTTP boundary. It derives read/discovery
  versus execution/mutation primitives and redacts authorization material in responses.
- `network_mcp` and `cloud_mcp` are the active sample MCP topology in Compose, with
  read/write/admin placeholder tools backed by shared `mcp_runtime` metadata.
- `agent_service_supervisor` is intentionally reduced to Auth0 Management API metadata
  loading. It no longer owns subagent discovery, workflow planning, workflow restoration, or
  workflow approval execution.

Runtime flow:

1. The sample frontend requires Auth0 Universal Login through Authorization Code + PKCE before
   rendering the assistant UI.
   `/api/auth/callback` validates Auth0 tokens with JWKS, stores only a signed httpOnly
   session cookie, and forwards a sanitized user session context to the supervisor.
2. The supervisor maps Auth0 user metadata into MCP workflow scopes and tool allow-lists,
   derives a display-only persona summary, and emits the `on_login` event.
3. The frontend reads only the returned session summary (`token_ref`, scopes,
   allowed tools, user identity, and persona) and renders the persona greeting before the first
   workflow request.
4. The assistant-ui runtime uses `HttpAgent({ url: "/api/ag-ui" })`. The authenticated
   Next.js proxy strips sensitive AG-UI payload keys, injects only sanitized session context,
   and forwards to `ag_ui_gateway` over HTTP/SSE.
5. `agent_service` applies a Coordinator/Dispatcher boundary: the Google ADK coordinator emits
   assistant narration and `ToolIntent` records, then the server-side dispatcher validates those
   intents against `workflow_core` contracts before any workflow state is persisted.
6. Workflow core validates tool metadata, materializes scopes from arguments, evaluates
   blast-radius policy, hashes the plan, and emits a `WorkflowPolicyDecision`.
7. If HITL is required, AG-UI streams a custom approval event with human-readable policy
   descriptions from tool metadata. The browser restores workflow state through
   `/api/workflows/{workflow_id}` and posts approval decisions through
   `/api/workflows/{workflow_id}/approve`; those Next.js routes read the signed Auth0 session
   cookie and delegate to Agent Service with user/session-bound parameters.
8. Approval execution is modeled inside Agent Service as approved-manifest validation, token
   context lookup, Auth0 OBO token exchange, and egress-gateway MCP dispatch.
9. Services post agentic traces to `/v1/traces` and logs to `/v1/logs` on the
   observability sidecar. Tests and operators can inspect `/v1/stats`, `/v1/telemetry`,
   `/v1/monitor/components`, and `/v1/monitor/event-types`.

The current implementation remains a local scaffold. It has service boundaries for AG-UI,
ADK-backed agent intent planning, Redis-backed state, egress policy, and Network/Cloud MCP
metadata; full durable execution hardening and live OBO integration remain future work.

## Shared Runtime Conventions

- Runtime dependencies declared in `pyproject.toml` are imported directly. Do not wrap imports
  in `try/except` unless a future lazy import is required for a measured startup or optional
  dependency constraint.
- MCP services should import `FastMCP`, `require_any_scope`, `restricted`, and
  `get_workflow_authz` from `mcp_runtime`, not from FastMCP or duplicated local wrappers.
- Sample tool Auth0 scope candidates, workflow scope templates, scope argument names, and HITL
  descriptions live in `workflow_core.tool_catalog`. Agent Service maps known Auth0 runtime
  grants to argument-bound manifest scopes, for example `read:apps` to `read:client:{appid}`,
  and fails the planning request if a proposal cannot supply the required scope argument.
- Auth0 user metadata must supply non-empty `allowed_scopes` and `allowed_mcp_tools`; the
  sanitized session context carries that allow-list into Agent Service. Orchestration tools such
  as planning and inspection remain available so the workflow service boundary can still
  construct a manifest.
- Login persona is not an authorization input. Persona fields are derived from validated
  session profile fields and optional `app_metadata.magnum_opus` fields, emitted through
  `on_login`, and returned to the frontend only for assistant-ui presentation.
- Session state reuses canonical workflow models from `workflow_core` instead of redeclaring
  workflow plan, step, status, or approval shapes.
- Agent Service state is keyed by tenant/user/session identifiers. The reference runtime uses
  Redis, requires `REDIS_URL`, and fails closed instead of rescuing Redis errors with
  process-local memory. The in-memory store is only available behind an explicit test flag.
- Agent Service owns the model-provider boundary behind Google ADK. `ANTHROPIC_API_KEY` and
  `ANTHROPIC_MODEL` configure ADK's direct Claude adapter; the local default is
  `claude-haiku-4-5-20251001`. `GOOGLE_ADK_MODEL` can override the ADK model. Missing or
  disabled ADK runtime configuration fails the run instead of falling back to local keyword
  routing. The coordinator consumes sanitized `tool_contracts` from the prompt and does not
  register ADK function tools, so tool execution remains behind Agent Service workflow dispatch.
  Slow or empty ADK responses fail the run instead of leaving the browser in an indefinite pending
  state.
- The legacy supervisor `WorkflowOrchestrator`, SQLite subagent discovery layer, and standalone
  planner/authorizer/executor services have been removed. Missing coordinator/runtime
  configuration fails inside Agent Service rather than falling back to compatibility proposals.

## Browser and AG-UI Boundary

The browser-visible service contract is intentionally narrow:

- `/api/auth/*` owns Auth0 login, callback, session, and logout. The browser-visible session
  type never includes server-only token context.
- `/api/threads` and `/api/threads/{thread_id}` create and restore Agent Service thread state
  for the active authenticated user/session.
- `/api/ag-ui` is the only browser chat/run boundary. It removes sensitive keys such as
  `auth_context_ref`, OAuth tokens, authorization headers, endpoint configuration, passwords,
  and client secrets before forwarding AG-UI state.
- `/api/workflows/{workflow_id}` and `/api/workflows/{workflow_id}/approve` restore and approve
  workflows through Agent Service. The browser supplies approval intent and `plan_hash`; the
  Next.js route supplies the authenticated user/session identity.

Approval presentation should stay at the typed workflow/tool-summary layer. Internal workflow
ids, plan hashes, step ids, and raw payload JSON are routing/diagnostic fields, not primary UX
labels.

## Login Persona Contract

`POST /identity/auth0/session` returns a `UserPersona` alongside the token reference and
authorization summary. The route accepts only a validated user session context from the Next.js
Auth0 callback boundary; it does not accept user passwords, user client secrets, raw access
tokens, ID tokens, refresh tokens, or authorization headers.

- `display_name`: Stable display label derived from `app_metadata.magnum_opus.display_name`,
  validated profile name/nickname, email prefix, or Auth0 subject.
- `headline`: Short summary for the Auth0 login panel and assistant welcome.
- `greeting`: Assistant-facing welcome text shown after login.
- `traits`: Small set of non-secret user/session facts, either from
  `app_metadata.magnum_opus.persona_traits` or derived browser-safe facts like email, scope
  count, and MCP tool count.

The frontend never receives raw Auth0 tokens. It receives `token_ref` and persona metadata,
while Next.js keeps the server-only token context behind API routes. The supervisor remains
responsible for Management API metadata reads and emitting `on_login`; Agent Service owns
thread/workflow state, approval validation, OBO lookup, and execution delegation.
