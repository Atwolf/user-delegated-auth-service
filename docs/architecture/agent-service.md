# Agent Service Architecture

The service is organized around Pydantic v2 contracts:

- `a2a_runtime` validates inter-agent envelopes and typed payloads.
- `workflow_core` owns workflow plans, steps, authorization bundles, scope materialization, and
  deterministic plan hashing. It also owns the `ToolIntent`, `WorkflowPolicyDecision`, and
  `EgressRequest` contracts used between the AG-UI gateway, agent service, egress gateway, and
  MCP services.
- `agent_runtime` owns invocation context, protocol interfaces, and shared FastAPI app helpers
  for sample agents.
- `mcp_runtime` owns the FastMCP integration surface used by MCP services: direct FastMCP
  imports, Auth0-compatible runtime scope checks, and workflow authorization decorators.
- `session_state` owns Redis-backed session/workflow state contracts.
- `token_broker` owns OBO token exchange request/response contracts.
- `observability` owns redaction-safe event emission helpers.
- `observability_sidecar` receives agentic traces and log payloads over HTTP, redacts
  sensitive fields, and exposes bounded recent telemetry for tests and local monitoring.
- `apps/frontend` is a standalone Next.js assistant-ui sample for Auth0 user-scoped workflow
  approval and persona-aware login greetings.
- `ag_ui_gateway` exposes the target `/agent` HTTP/SSE boundary and adapts AG-UI-like run
  input into Agent Service workflow planning calls.
- `chainlit_middleware` is the legacy compatibility boundary for Chainlit Copilot-style
  message events; it forwards user messages into the AG-UI gateway.
- `agent_service` is the target Coordinator/Dispatcher runtime boundary. The POC uses
  deterministic intent-only Network Services and Cloud Operations subagents plus a process-local
  `InMemoryStateStore`; it does not require the Google ADK package during tests.
- `egress_gateway` is the only modeled outbound MCP/HTTP boundary. It derives read/discovery
  versus execution/mutation primitives and redacts authorization material in responses.
- `network_mcp` and `cloud_mcp` replace the old sample MCP topology in Compose with
  read/write/admin placeholder tools backed by shared `mcp_runtime` metadata.

Runtime flow:

1. The sample frontend requires Auth0 Universal Login through Authorization Code + PKCE.
   `/api/auth/callback` validates Auth0 tokens with JWKS, stores only a signed httpOnly
   session cookie, and forwards a sanitized user session context to the supervisor.
2. The supervisor maps Auth0 user metadata into MCP workflow scopes and tool allow-lists,
   derives a display-only persona summary, and emits the `on_login` event.
3. The frontend reads only the returned session summary (`token_ref`, scopes,
   allowed tools, user identity, and persona) and renders the persona greeting before the first
   workflow request.
4. UI Pod 1 sends AG-UI-style run input to `ag_ui_gateway` over HTTP/SSE. UI Pod 2 can send a
   Chainlit-compatible message event to `chainlit_middleware`, which forwards the same AG-UI
   payload shape.
5. `agent_service` applies a Coordinator/Dispatcher boundary: Network Services and Cloud
   Operations subagents propose `ToolIntent` records only; they do not execute tools.
6. Workflow core validates tool metadata, materializes scopes from arguments, evaluates
   blast-radius policy, hashes the plan, and emits a `WorkflowPolicyDecision`.
7. If HITL is required, AG-UI streams a custom approval event with human-readable descriptions
   from tool metadata. Approval execution is modeled as token exchange plus egress-gateway MCP
   dispatch; the legacy supervisor approval route now records approval and delegates execution
   instead of fabricating step results in-router.
8. Services post agentic traces to `/v1/traces` and logs to `/v1/logs` on the
   observability sidecar. Tests and operators can inspect `/v1/stats`, `/v1/telemetry`,
   `/v1/monitor/components`, and `/v1/monitor/event-types`.

The current implementation remains a local scaffold. It has service boundaries for AG-UI,
Chainlit compatibility, agent intent planning, egress policy, and Network/Cloud MCP metadata;
full durable execution and live OBO integration remain future work.

## Shared Runtime Conventions

- Runtime dependencies declared in `pyproject.toml` are imported directly. Do not wrap imports
  in `try/except` unless a future lazy import is required for a measured startup or optional
  dependency constraint.
- MCP services should import `FastMCP`, `require_any_scope`, `restricted`, and
  `get_workflow_authz` from `mcp_runtime`, not from FastMCP or duplicated local wrappers.
- Sample tool Auth0 scope candidates, workflow scope templates, scope argument names, and HITL
  descriptions live in `workflow_core.tool_catalog`. Supervisor planning maps known Auth0
  runtime grants to argument-bound manifest scopes, for example `read:apps` to
  `read:client:{appid}`, and fails the planning request if a proposal cannot supply the
  required scope argument.
- When Auth0 user metadata supplies `allowed_mcp_tools`, the supervisor filters discovered
  proposals before manifest construction. Orchestration tools such as planning and inspection
  remain available so the workflow service boundary can still construct a manifest.
- Login persona is not an authorization input. Persona fields are derived from validated
  session profile fields and optional `app_metadata.magnum_opus` fields, emitted through
  `on_login`, and returned to the frontend only for assistant-ui presentation.
- Session state reuses canonical workflow models from `workflow_core` instead of redeclaring
  workflow plan, step, status, or approval shapes.
- The legacy supervisor `WorkflowOrchestrator` no longer synthesizes fallback proposals. Missing
  discovery records or failed subagent capability calls produce no proposals, so the old
  compatibility surface fails closed.

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
  `app_metadata.magnum_opus.persona_traits` or deterministic fallbacks like email, scope count,
  and MCP tool count.

The frontend never receives raw Auth0 tokens. It receives `token_ref` and persona metadata,
while the supervisor remains responsible for Management API metadata reads, emitting `on_login`,
and making all authorization decisions from scopes, metadata, and workflow manifests.
