# Remediation TODO

This file captures independent review findings that are intentionally deferred to future remediation branches.

## P0/P1 security boundaries

- Keep raw Auth0 bearer tokens out of browser-held cookies. Store bearer material server-side behind `tokenRef` / `sessionId` or a token-broker cache reference, and pass only sanitized session context across browser-facing boundaries.
  - Target browser cookie shape: `sessionId`, `tokenRef`, `scope`, `audience`, `expiresAt`, `userId`, `userEmail`, `allowedTools`, `persona`, and non-secret metadata only.
  - Target trusted registry shape: `token_ref`, `session_id`, `user_id`, `audience`, `scopes`, `expires_at`, and encrypted/secret raw `access_token`.
  - Planned implementation: add a server-side Auth0 token registry, remove `authContextRef` from frontend session types/cookies, stop forwarding `auth_context_ref` through chat/AG-UI/Chainlit, and resolve the subject token behind Agent Service/token-broker during OBO.
  - Acceptance criteria: browser-held cookies never contain compact JWTs or raw bearer sentinels; planning and AG-UI carry only `token_ref`, `session_id`, scopes, and allow-list; OBO still succeeds by resolving a trusted token record; legacy bearer-bearing cookies are invalidated or sanitized.
- Bind workflow reads and approvals to the active authenticated user/session. Replace process-global workflow cache access with uid/session-keyed state backed by Redis for the POC and the production path.
- Require approved execution grants at egress. Egress must validate workflow id, approval id, plan hash, target tool, arguments, scopes, and token audience against an approved manifest before dispatching to MCP.
- Authenticate the Agent Service approval boundary. Reject approvals for the wrong user/session, stale statuses, completed workflows, and caller-supplied identity claims that do not match the stored workflow owner.
- Request only scopes covered by the human-approved manifest, or introduce an explicit least-privilege mapping from workflow scopes to Auth0 API permissions and verify returned token scope is not broader than approval.
- Fail closed for unknown tool authorization. Unknown tool names must be rejected except for exact `inspect_request` fallback planning.
- Restore equivalent WRITE/ADMIN scope enforcement for Network/Cloud MCP tools, either at MCP tool auth or at egress with JWT audience/scope validation.
- Reject unvalidated caller-supplied AG-UI state. Direct AG-UI gateway calls must require validated server-derived session context or service-to-service auth.

## Protocol and UX correctness

- Emit AG-UI-compliant message and state events: message start/content/end with stable message ids, plus valid state snapshot or JSON Patch deltas.
- Route Chainlit approvals through the protocol boundary instead of constructing Agent Service approval payloads in the compatibility middleware.
- Parse AG-UI SSE as a stream using a real line-oriented parser. Cover CRLF, comments, no-space fields, multiline data, chunk boundaries, non-2xx responses, and timeout behavior.
- Emit AG-UI `RUN_ERROR` events when planning or gateway execution fails after `RUN_STARTED`.
- Enforce signed session-cookie expiry in Chainlit middleware or share the frontend session parser.
- Reject protocol-relative or absolute Auth0 `returnTo` values; allow only same-origin path/query targets.
- Render malformed workflow step payloads safely instead of parsing `input_payload_json` directly during React render.

## Runtime and test hardening

- Make failed MCP calls return non-2xx from egress and persist workflow status as `failed` rather than `completed`.
- Update egress contract tests from legacy `identity-mcp` fixtures to Network/Cloud MCP targets and cover MCP-call-enabled success/failure paths.
- Wire or document the `python-base` Docker image build path so a clean machine can build the full Compose topology.
- Add negative tests for direct gateway auth bypass, wrong-user workflow reads/approvals, insufficient MCP scopes, expired Chainlit cookies, and failed downstream execution.
