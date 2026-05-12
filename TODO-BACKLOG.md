# User Delegated Auth Service — Implementation Task Backlog

This task list turns the architecture review into an implementation-ready backlog. It assumes the repo is intended to model the enterprise target as closely and simply as possible before code is manually copied into the enterprise system.

## Current resolution status

| Item | Status | Resolution or deferral |
| --- | --- | --- |
| P0-1 | Solved | Browser-to-AG-UI now sends trusted identity only through signed internal headers. Browser-originated AG-UI state is stripped of identity/authz fields, AG-UI requires signed context, and forged state tests cover overwrite behavior. |
| P0-2 | Solved | Agent Service approvals resolve owner/approver from signed `SessionContext`; request-body `approved_by_user_id`, `user_id`, and `session_id` are ignored. Cross-user signed context returns not found. |
| P0-3 | Solved for POC | Workflow read, approval, thread restore, and execution now use signed user/session/tenant context. Agent Service supports tenant/user/session-scoped Redis state and Compose wires Redis; enterprise approval queues/event streams remain deferred under P1-4/P2-3. |
| P0-4 | Solved | `workflow_core.ExecutionGrant` is signed by Agent Service and verified at egress for signature, expiry, workflow, approval, tool, arguments, target MCP, scopes, audience, user, session, and tenant. Read and write MCP calls are grant-bound, and missing OBO audience fails closed. |
| P0-5 | Solved for POC | Browser cookie now contains only a signed session handle; raw Auth0 access material stays in server-side session storage and BFF responses strip sensitive fields. Auth0 Management API metadata loading now requires signed internal session context. Durable external session storage remains a productionization task under P1-4. |
| P0-6 | Solved | Approval expiry is enforced before Agent Service dispatch and again inside egress grant validation. |
| P1-1 | Partially solved | Frontend workflow lifecycle now targets Agent Service; Supervisor is reduced to identity metadata. Full model consolidation is tracked under P1-5. |
| P1-2 | Deferred | Direct Auth0 OBO client remains in Agent Service to keep this POC deployable. A generic broker seam is still the right enterprise porting task. |
| P1-3 | Solved | Agent runtime behavior is behind provider/runtime protocols. The default runtime now uses ADK directly, consumes sanitized `tool_contracts` without registering ADK function tools, and fails closed when the runtime is unavailable, so E2E cannot pass through keyword-routing compatibility behavior. |
| P1-4 | Partially solved | Agent Service has tenant/user/session-scoped Redis workflow/thread persistence and Compose pins the reference runtime to Redis. Redis errors no longer rescue through process-local memory, and the memory backend is gated behind an explicit test-only flag. Remaining enterprise work is externalized approval queue semantics, event stream durability, and production session storage. |
| P1-5 | Partially solved | `ExecutionGrant` moved to `workflow_core`; full `WorkflowRecord` consolidation is deferred because it is a larger API contract cleanup. |
| P1-6 | Partially solved | Legacy A2A, Chainlit, old agent pods, and obsolete MCP services have been deleted. Identity/developer/billing catalog entries remain as sample metadata-only tools for the current Auth0 persona; executable MCP registry consolidation remains under P2-4. |
| P1-7 | Solved | The frontend BFF strips assistant-runtime envelope extras before AG-UI, AG-UI forwards a strict canonical Agent Service payload, Agent Service redacts token refs from streamed assistant/tool strings, and the live browser smoke now renders assistant text plus a permitted tool chip while denying tools outside the active Auth0 identity metadata. |
| P1-8 | Open | Split Agent Runtime output into streamed assistant narration and final structured `tool_intents`. The LLM should be able to stream user-visible workflow explanation text while `tool_intents` remain the typed contract for workflow UI rendering and approval requests. |
| P2-1 | Deferred | SQL-backed long-term memory is outside the POC security-critical path. |
| P2-2 | Partially solved | Redaction was hardened across sidecar log messages, browser-visible workflow state, and AG-UI streamed assistant/tool strings. Durable audit sink and complete lifecycle event coverage remain enterprise work. |
| P2-3 | Deferred | Approval queue semantics are intentionally deferred; current requirement keeps same-user browser approval. |
| P2-4 | Partially solved | Egress now checks tool-to-target catalog alignment. Config-driven MCP registry remains deferred. |
| P2-5 | Deferred | PingFederate implementation is intentionally left as the enterprise substitution seam after P1-2. |
| P2-6 | Deferred | Idempotency strategy is not security-critical for this POC and should be designed with the enterprise workflow queue/store. |

The detailed sections below preserve the original task definitions for traceability. Treat the status table and remaining implementation order as authoritative for current work routing; solved sections are retained as acceptance criteria history, not active remediation prompts.

## P0 — Security and correctness blockers

### P0-1: Stop trusting caller-supplied identity in AG-UI state

**Issue**

The AG-UI gateway currently reads identity and authorization context from the request body state, including `user_id`, `tenant_id`, `session_id`, `token_ref`, `token_scopes`, `allowed_tools`, and `auth_context_ref`. This means a direct caller can potentially spoof identity or authorization by posting crafted AG-UI input.

**Where to fix**

- `services/ag_ui_gateway/ag_ui_gateway/models.py`
- `services/ag_ui_gateway/ag_ui_gateway/sse.py`
- `apps/frontend/app/api/ag-ui/route.ts`
- Any call path that forwards `RunAgentInput.state` into workflow planning.

**Scope**

- Make `RunAgentInput` strict. Do not allow arbitrary identity fields through `state`.
- Introduce a server-derived `SessionContext` model containing:
  - `tenant_id`
  - `user_id` or enterprise UID
  - `session_id`
  - `allowed_tools`
  - `token_ref`
  - `auth_context_ref`, if still needed
  - `correlation_id`
- Build `SessionContext` at the trusted gateway boundary from verified cookie/JWT/session data.
- Ensure downstream workflow code receives `SessionContext` as a trusted parameter, not as arbitrary AG-UI state.
- Add service-to-service authentication or signed internal headers between the frontend proxy and AG-UI gateway if they remain separate services.

**Validation**

- Unit test: POST to AG-UI gateway with forged `state.user_id`, `state.tenant_id`, and `state.allowed_tools`; verify these are ignored or rejected.
- Unit test: missing verified session context returns `401` or `403`.
- Integration test: valid browser login still produces a normal AG-UI run.
- Live browser validation:
  - Log in normally.
  - Send a chat prompt that produces a workflow.
  - Confirm workflow user and tenant match the authenticated user, not any user-supplied UI state.
- Negative browser/API validation:
  - Use dev tools or curl to inject a different `user_id` in AG-UI state.
  - Confirm the backend rejects the request or overwrites it with server-derived identity.

### P0-2: Bind workflow approval to the owning user and active session

**Issue**

The approval endpoint accepts an `approved_by_user_id` value and does not reliably prove that the approver is the same authenticated user who owns the workflow. For your current target, the initiating user is the approver, so cross-user approval must be rejected.

**Where to fix**

- `services/agent_service/agent_service/app.py`
- Approval endpoint: `/workflows/{id}/approve`
- Workflow model and approval request model locations under `services/agent_service/agent_service/models.py` and/or canonical `workflow_core` models after consolidation.

**Scope**

- Remove trust in request-body `approved_by_user_id`.
- Resolve approver from verified `SessionContext`.
- Validate:
  - `record.tenant_id == ctx.tenant_id`
  - `record.user_id == ctx.user_id`
  - `record.session_id == ctx.session_id`, unless cross-session approval is explicitly allowed.
- Reject mismatches with `403`.
- Add audit event for approval rejection.

**Validation**

- Unit test: owner approves workflow successfully.
- Unit test: different user attempts approval and receives `403`.
- Unit test: same user but wrong tenant receives `404` or `403`, depending on chosen tenant-boundary semantics.
- Live browser validation:
  - Create a high-risk workflow.
  - Approve it from the same logged-in session.
  - Confirm success.
- API validation:
  - Replay the approval request with a different claimed user ID.
  - Confirm the server ignores the claim and rejects based on verified session context.

### P0-3: Enforce tenant boundaries on workflow read, approve, and execute

**Issue**

`tenant_id` is present in models, but workflow lookup is effectively by `workflow_id`. In a multi-tenant system with UID-keyed session state, every workflow access must be tenant-scoped.

**Where to fix**

- `services/agent_service/agent_service/app.py`
- `services/agent_service/agent_service/state.py`, until replaced by Redis
- `services/supervisor/agent_service_supervisor/routes.py`, if retained
- `packages/session_state/key_builder.py`
- Future canonical workflow store facade.

**Scope**

- Introduce a `TenantGuard` or equivalent helper.
- Require tenant match on:
  - workflow fetch
  - workflow approval
  - workflow execution
  - workflow event stream retrieval
- Prefer tenant-scoped keys, for example:
  - `tenant:{tenant_id}:user:{uid}:session:{session_id}`
  - `tenant:{tenant_id}:workflow:{workflow_id}`
- Decide whether cross-tenant access should return `404` or `403`. For enterprise systems, `404` is often preferable to avoid confirming object existence.

**Validation**

- Unit test: workflow created under tenant A cannot be read from tenant B.
- Unit test: workflow created under tenant A cannot be approved from tenant B.
- Unit test: Redis keys include tenant prefix after Redis store is wired.
- Integration test: two simulated tenants with same UID and session ID do not collide.
- Live browser validation, if the app can simulate tenants:
  - Log in under tenant A, create workflow.
  - Switch to tenant B or alter tenant context.
  - Confirm workflow is inaccessible.

### P0-4: Add `ExecutionGrant` validation at egress

**Issue**

The egress gateway receives tool execution requests but does not fully revalidate that the request matches an approved plan. It should not rely solely on the workflow service saying the call is approved.

**Where to fix**

- `services/egress_gateway/egress_gateway/app.py`
- `services/egress_gateway/egress_gateway/models.py`
- New module: `services/egress_gateway/egress_gateway/grant_validator.py`
- Workflow approval/execution code in `services/agent_service/agent_service/app.py`
- Canonical model package, ideally `packages/workflow_core` or new `packages/policy/grant.py`.

**Scope**

- Define an `ExecutionGrant` model with:
  - `tenant_id`
  - `workflow_id`
  - `approval_id`
  - `plan_hash`
  - `step_id`
  - `tool_name`
  - `arguments`
  - `target_mcp`
  - `required_scopes`
  - `audience`
  - `expires_at`
  - `approved_by`
  - `correlation_id`
- At egress, validate:
  - grant exists
  - grant is not expired
  - workflow and approval are still valid
  - `plan_hash` matches approved plan
  - requested tool and arguments match approved step
  - token scopes include required scopes
  - token audience matches target MCP or downstream resource
  - tenant and user context match
- Add clear denial audit events.

**Validation**

- Unit test: valid grant dispatches.
- Unit test: expired grant is rejected.
- Unit test: modified arguments are rejected.
- Unit test: wrong tool name is rejected.
- Unit test: missing scope is rejected.
- Unit test: wrong audience is rejected.
- Integration test: approve a workflow, then execute through egress successfully.
- Negative API validation:
  - Capture an egress request.
  - Modify one argument or target MCP.
  - Confirm egress rejects it before calling the MCP.

### P0-5: Remove raw bearer material and sensitive auth references from browser cookies

**Issue**

The current auth flow stores or forwards sensitive auth context through browser-visible or browser-originating state. The enterprise target should keep token material server-side and use opaque references.

**Where to fix**

- `apps/frontend/app/api/auth/callback/route.ts`
- `apps/frontend/lib/server/auth0-*.ts`
- `apps/frontend/app/api/ag-ui/route.ts`
- `services/supervisor/agent_service_supervisor/routes.py`, if retained
- Token reference handling in agent service.

**Scope**

- Store sensitive token material only in server-side storage.
- Browser cookie should contain only a signed session reference or platform-standard session cookie.
- Introduce a token registry keyed by `token_ref`.
- Ensure `token_ref` is bound to:
  - tenant
  - user
  - session
  - expiry
  - allowed audience/scope metadata
- Do not place bearer tokens, refresh tokens, or raw authorization context in AG-UI state.

**Validation**

- Unit test: serialized cookie does not contain access token, refresh token, or raw bearer values.
- Integration test: token exchange still succeeds using server-side token registry.
- Live browser validation:
  - Log in.
  - Inspect cookies and local/session storage in dev tools.
  - Confirm no bearer tokens or raw auth context are present.
- Security validation:
  - Attempt to reuse `token_ref` from another session.
  - Confirm rejection.

### P0-6: Enforce approval expiry before execution

**Issue**

Approved workflows have an expiry timestamp, but execution does not consistently enforce it at the final egress boundary.

**Where to fix**

- `services/agent_service/agent_service/app.py`
- `services/egress_gateway/egress_gateway/app.py`
- New `ExecutionGrant` validator.

**Scope**

- Enforce `expires_at` in workflow service before execution.
- Enforce `expires_at` again at egress.
- Return a clear status such as `approval_expired`.
- Emit audit event for expired approval.
- Require user to re-approve expired workflow.

**Validation**

- Unit test: approval before expiry executes.
- Unit test: approval after expiry fails.
- Integration test: create approval with short TTL, wait for expiry, attempt execute, confirm rejection.
- Live browser validation:
  - Create a high-risk workflow.
  - Wait past approval TTL.
  - Click approve or execute.
  - Confirm UI shows expired/retry state.

## P1 — Structural cleanup and enterprise seams

### P1-1: Consolidate supervisor and agent service ownership

**Issue**

The repo currently has two parallel workflow-capable services: `services/supervisor` and `services/agent_service`. They define separate workflow records, keep separate state, and own overlapping endpoints. This is the largest source of confusion for manual porting.

**Where to fix**

- `services/supervisor/`
- `services/agent_service/`
- `services/ag_ui_gateway/ag_ui_gateway/client.py`
- Frontend API routes that call supervisor or agent service.

**Scope**

Choose one target shape:

1. **Preferred:** single `workflow_service` owns planning, approval, execution, workflow state, and workflow events.
2. **Alternative:** split into a narrow `identity_service` and a `workflow_service`, with no workflow lifecycle in identity service.

Then:

- Move canonical workflow lifecycle into one service.
- Remove duplicate `/workflows/plan` and `/workflows/{id}/approve` implementations.
- Collapse duplicate `WorkflowRecord` definitions into one canonical model.
- Update AG-UI gateway and frontend routes to call the single owner.

**Validation**

- Unit test: one canonical workflow model is used by planning, approval, execution, and SSE serialization.
- Static validation: no duplicate `WorkflowRecord` definitions remain outside test fixtures.
- Integration test: login, chat, plan, approval, execution all work through the chosen service.
- Live browser validation:
  - Complete the full workflow from chat prompt to approval to result.
  - Confirm no supervisor-only and agent-service-only state divergence.

### P1-2: Introduce `TokenBroker` as the PingFederate substitution seam

**Issue**

The repo has a useful token broker package, but services instantiate Auth0-specific clients directly. This makes PingFederate substitution harder and spreads IdP logic through service code.

**Where to fix**

- `packages/token_broker/protocols.py`
- `packages/token_broker/models.py`
- `packages/token_broker/auth0.py`
- `services/agent_service/agent_service/app.py`
- Any supervisor Auth0 metadata/token calls if retained.

**Scope**

- Define or refine a single `TokenBrokerClient` protocol for workflow token exchange.
- Refactor workflow service to depend on `TokenBrokerClient`, not `Auth0OnBehalfOfClient`.
- Keep Auth0 implementation as local test/demo implementation.
- Add placeholder or skeletal `pingfederate.py` with the same interface, even if enterprise credentials are not available.
- Pass requested audience and materialized scopes explicitly.
- Ensure the broker response includes expiry, scopes, audience, subject, actor, and token reference metadata.

**Validation**

- Unit test: workflow service can use a fake token broker.
- Unit test: Auth0 broker implementation still works in demo mode.
- Unit test: token request includes materialized scopes and target audience.
- Static validation: no direct `Auth0OnBehalfOfClient` construction in workflow business logic.
- Future enterprise validation:
  - Swap in PingFederate implementation without changing workflow service code.

### P1-3: Introduce `AgentRuntime` and move current intent matcher behind it

**Issue**

The target is Google ADK, but the repo currently uses a hand-rolled `IntentOnlyAgent` keyword matcher. The keyword matcher can remain useful as a local test double, but it should not be the architectural shape.

**Where to fix**

- `services/agent_service/agent_service/agents.py`
- `packages/agent_runtime/`
- New package: `packages/adk_runtime/`
- Workflow planning code in `services/agent_service/agent_service/app.py` or future `workflow_service/planner.py`.

**Scope**

- Define an `AgentRuntime` protocol:
  - `plan(question, session_context) -> list[ToolProposal]`
  - optionally `stream(...) -> AsyncIterator[AgentEvent]` if needed later.
- Move current keyword matcher into `IntentOnlyRuntime` or `TestAgentRuntime`.
- Add `ADKMultiAgentRuntime` stub with clear constructor and TODOs for enterprise ADK integration.
- Ensure workflow service only depends on `AgentRuntime`.
- Keep AG-UI event translation outside the runtime.

**Validation**

- Unit test: workflow service works with fake runtime.
- Unit test: current keyword matcher produces same proposals through the new interface.
- Static validation: workflow planner does not import concrete intent agents directly.
- Future validation:
  - Swap `IntentOnlyRuntime` for ADK runtime with no workflow-service changes.

### P1-4: Wire Redis session state and remove process-local stores

**Issue**

The repo includes a complete Redis session state package, and Compose starts Redis, but services still use process-local dicts. That does not model enterprise multi-instance behavior.

**Where to fix**

- `packages/session_state/`
- `services/agent_service/agent_service/state.py`
- `services/supervisor/agent_service_supervisor/routes.py`, if retained
- Docker Compose/service configuration.

**Scope**

- Use `RedisSessionStateStore` for:
  - session state
  - workflow records
  - event streams
  - approval state, until SQL queue exists
- Remove or restrict `InMemoryStateStore` to tests only.
- Ensure keys include tenant and UID.
- Configure Redis URL via environment.
- Preserve optimistic concurrency behavior for workflow updates.

**Validation**

- Unit test: state store writes and reads workflow by tenant/user/session.
- Integration test: create workflow, restart workflow service, fetch workflow successfully.
- Integration test: two service instances see same workflow state.
- Redis validation:
  - Inspect keys and confirm tenant/UID/session prefixing.
- Live browser validation:
  - Create workflow.
  - Restart backend container.
  - Refresh UI and confirm workflow state can be recovered.

### P1-5: Collapse workflow models into `workflow_core`

**Issue**

There are duplicate workflow models in supervisor and agent service. The repo should have one canonical enterprise workflow contract.

**Where to fix**

- `services/agent_service/agent_service/models.py`
- `services/supervisor/agent_service_supervisor/workflow_api_models.py`
- `packages/workflow_core/workflow_core/models.py`
- `services/ag_ui_gateway/ag_ui_gateway/sse.py`

**Scope**

- Move canonical `WorkflowRecord`, `WorkflowStatus`, `WorkflowStep`, `Approval`, and event/timeline models into `packages/workflow_core`.
- Prefer the richer supervisor-style record if it includes events, authorization, and structured status.
- Update services to import canonical models.
- Remove defensive serializer logic that exists only to support two model shapes.

**Validation**

- Static validation: only one production `WorkflowRecord` definition exists.
- Unit test: workflow record serializes consistently for REST and AG-UI state delta.
- Integration test: plan, approve, execute, and fetch workflow using canonical model.

### P1-6: Delete confirmed dead and legacy code

**Issue**

Dead code increases manual porting cost and makes the reference architecture harder to understand.

**Where to fix**

- `services/chainlit_middleware/`
- `services/agents/planner/`
- `services/agents/executor/`
- `services/agents/authorizer/`
- `services/mcps/billing_mcp/`
- `services/mcps/developer_mcp/`
- `services/mcps/identity_mcp/`
- Supervisor persona builder, if not required.
- Compose files and docs referencing these services.

**Scope**

- Delete services not used by the target architecture.
- Remove Compose entries, environment variables, docs, and test references.
- Remove unused catalog entries if their MCPs are deleted.
- Keep only network/cloud MCPs if they are the active examples.

**Validation**

- Static validation: no imports or Compose references to deleted services.
- Test validation: full test suite passes.
- Docker validation: Compose starts only target-relevant services.
- Live browser validation:
  - Login and chat flow works after deletion.
  - Approval/execution still works for retained MCPs.

### P1-7: Improve AG-UI SSE correctness and error handling

**Issue**

The current SSE implementation emits a limited success path and lacks robust error events. If planning or execution fails, the UI needs a standard error event rather than a broken stream.

**Where to fix**

- `services/ag_ui_gateway/ag_ui_gateway/sse.py`
- `services/ag_ui_gateway/ag_ui_gateway/app.py`
- Any frontend AG-UI event handling.

**Scope**

- Emit `RUN_ERROR` or equivalent AG-UI-compatible error event on exceptions.
- Include stable run ID, message ID, and correlation ID in events.
- Ensure stream always terminates cleanly.
- If any SSE parser remains, make it line-oriented and handle:
  - CRLF
  - comments
  - multi-line `data:`
  - chunk boundaries
- Add tests for streaming failure paths.

**Validation**

- Unit test: successful run emits started, content/state, finished.
- Unit test: planning exception emits run error and closes stream.
- Unit test: execution exception emits run error and closes stream.
- Live browser validation:
  - Trigger a normal prompt and confirm streamed response.
  - Trigger a controlled backend error and confirm UI shows error without hanging.

### P1-8: Stream assistant narration separately from workflow tool intents

**Issue**

The current AG-UI transport streams run lifecycle events, but LLM text does not stream token-by-token
or chunk-by-chunk. Agent Service waits for the ADK coordinator to finish, parses a complete JSON
object with `assistant_message` and `tool_intents`, then emits one `TEXT_MESSAGE_CONTENT` event with
the full `assistant_message`. That makes chat bubbles appear as a single completed message even
though the SSE transport is active.

The target runtime should separate the user-visible narration channel from the workflow-intent
channel:

- `assistant_message` or equivalent assistant narration can stream incrementally as normal LLM text.
- `tool_intents` remain structured, finalizable output used to render workflow/tool UI elements and
  request human approval.
- Workflow dispatch still treats `tool_intents` as the authoritative typed planning contract; streamed
  prose is explanatory and must not authorize execution.

**Where to fix**

- `services/agent_service/agent_service/providers.py`
- `services/agent_service/agent_service/app.py`
- `services/ag_ui_gateway/ag_ui_gateway/sse.py`
- `apps/frontend/components/assistant-root.tsx`
- `apps/frontend/tests/assistant-runtime.test.tsx`
- `services/agent_service/tests/test_app.py`
- `services/ag_ui_gateway/tests/test_app.py`

**Scope**

- Replace or extend `AgentRuntimeProvider.run()` with a streaming runtime contract, for example:
  - `stream(context, allowed_tool_names, available_tool_names) -> AsyncIterator[AgentRuntimeEvent]`
  - events for assistant text deltas, final structured intents, provider errors, and completion.
- Keep the final typed `tool_intents` event distinct from text deltas. Do not ask the UI to parse JSON
  out of assistant prose.
- Update the ADK prompt/runtime contract so narration can be emitted naturally while structured
  intents are emitted as a final machine-readable payload or side-channel event.
- Emit `TEXT_MESSAGE_START` before waiting for the final planning payload, then forward safe assistant
  text deltas as they arrive.
- Accumulate and redact streamed text before browser emission; preserve current secret/token redaction
  guarantees.
- Continue to create workflow state, tool-call UI, and approval requests only after typed
  `tool_intents` are finalized and dispatched.
- Avoid fake streaming that chunks a fully completed `assistant_message` after the model call has
  already finished. That may animate the bubble but does not improve latency or model observability.

**Validation**

- Unit test: provider text deltas emit multiple `TEXT_MESSAGE_CONTENT` events before final intent
  dispatch.
- Unit test: final `tool_intents` still create the same workflow/tool-call UI as today.
- Unit test: streamed text containing token refs, bearer values, or auth context is redacted before
  browser emission.
- Unit test: malformed or missing final intent payload emits `RUN_ERROR` without leaving a hanging
  assistant message.
- Browser smoke:
  - Log in through Auth0.
  - Send a prompt that triggers workflow planning.
  - Confirm assistant text appears incrementally before the final tool chip/approval UI.
  - Confirm the final tool chip and approval request come from `tool_intents`, not parsed prose.

## P2 — Enterprise fidelity improvements

### P2-1: Add SQL-backed long-term user memory interface

**Issue**

The target includes user-scoped memory. The repo currently has no durable long-term memory abstraction beyond session state.

**Where to fix**

- New package or module:
  - `packages/session_state/sql_long_term_store.py`, or
  - `packages/memory/`
- Workflow service planner/runtime context assembly.

**Scope**

- Define `LongTermMemoryStore` protocol:
  - `append(tenant_id, uid, memory_item)`
  - `list_recent(tenant_id, uid, limit)`
  - optionally `search(tenant_id, uid, query, limit)`
- Start with SQL JSONB rows if semantic search is not required.
- Keep memory scoped to `tenant_id + uid`.
- Add provenance, timestamps, source workflow/message IDs, and TTL or retention class.

**Validation**

- Unit test: user A cannot read user B memory.
- Unit test: tenant A cannot read tenant B memory.
- Integration test: memory persists across service restart.
- Live browser validation:
  - Store a user-scoped preference or remembered fact.
  - Start a new session.
  - Confirm agent can use that memory.

### P2-2: Replace in-memory observability sidecar with durable audit sink

**Issue**

The sidecar is useful for demos but does not model enterprise audit requirements. Audit events should be durable and redacted before persistence.

**Where to fix**

- `packages/observability/`
- `services/observability_sidecar/`
- Workflow service event emission
- Egress gateway event emission
- Approval handling.

**Scope**

- Define `AuditSink` protocol.
- Implement a SQL or enterprise logging sink test double.
- Emit durable events for:
  - run started/finished/error
  - workflow planned
  - approval requested/approved/rejected/expired
  - token exchange requested/succeeded/failed
  - egress allowed/denied/dispatched
  - downstream result
- Ensure redaction happens before persistence.

**Validation**

- Unit test: sensitive fields are redacted before sink append.
- Integration test: workflow lifecycle creates expected audit records.
- Failure test: denied egress emits denial audit event.
- Live browser validation:
  - Complete a workflow.
  - Query audit sink and confirm end-to-end correlation ID.

### P2-3: Convert HITL into an approval queue

**Issue**

The current HITL flow is a synchronous browser re-POST. Your current requirement says the initiating user approves, but a queue still models enterprise behavior better and makes timeout/retry semantics explicit.

**Where to fix**

- Workflow service approval module
- New `ApprovalQueue` interface
- Redis and/or SQL backing store
- Frontend approval UI route.

**Scope**

- Create `PendingApproval` records with:
  - approval ID
  - tenant
  - user
  - session
  - workflow ID
  - plan hash
  - exact materialized steps
  - expiry
  - status
- Add `/approvals/{id}/decide`.
- Keep same-user constraint for now.
- Support timeout to expired/declined.
- Emit state delta to UI when approval is pending.

**Validation**

- Unit test: pending approval is created for medium/high blast radius.
- Unit test: same user can approve.
- Unit test: other user cannot approve.
- Unit test: expired approval cannot be approved.
- Live browser validation:
  - Prompt for a high-risk action.
  - Confirm approval card appears.
  - Approve.
  - Confirm execution proceeds.

### P2-4: Replace hard-coded MCP routing with a registry

**Issue**

The egress gateway currently hard-codes MCP target URLs. Adding tools or domains should not require code changes.

**Where to fix**

- `services/egress_gateway/egress_gateway/app.py`
- New `mcp_dispatcher.py` or registry module
- Tool catalog in `packages/workflow_core`.

**Scope**

- Add a registry mapping `target_mcp` or `downstream_audience` to endpoint, allowed tools, and health status.
- Load registry from config for local demo.
- Keep enterprise interface compatible with existing IAM/resource registry if applicable.
- Validate target exists and tool is allowed on that target before dispatch.

**Validation**

- Unit test: known MCP target resolves.
- Unit test: unknown MCP target is rejected.
- Unit test: tool not allowed for target is rejected.
- Integration test: add a new mock MCP through config only and dispatch to it.

### P2-5: Prepare PingFederate implementation

**Issue**

Even if this repo remains Auth0-backed locally, it should show exactly where PingFederate token exchange will plug in.

**Where to fix**

- `packages/token_broker/pingfederate.py`
- `packages/token_broker/models.py`
- Workflow service token exchange call site.
- Config/env templates.

**Scope**

- Add PingFederate-specific config model:
  - token endpoint
  - client ID
  - client auth method
  - subject token type
  - actor token source
  - requested token type
  - default audience/resource handling
- Implement request construction but allow mocked response for local tests if real PingFederate is unavailable.
- Ensure no workflow code depends on PingFederate-specific fields.

**Validation**

- Unit test: PingFederate token exchange request body includes expected grant type, subject token, actor token, audience/resource, and scopes.
- Unit test: PingFederate response maps into generic `WorkflowToken`.
- Static validation: workflow service imports only generic `TokenBrokerClient`.
- Enterprise validation:
  - Run against PingFederate dev tenant.
  - Confirm downstream app sees subject and actor/delegation claims.

### P2-6: Add idempotency strategy for workflow creation and execution

**Issue**

The current workflow ID appears content-derived, which can cause duplicate prompts in the same session to reuse workflow IDs unexpectedly. Enterprise behavior should be explicit.

**Where to fix**

- Workflow ID generation helper in agent service
- Workflow model
- Approval/execution code
- State store.

**Scope**

- Decide desired behavior:
  - unique workflow per prompt, or
  - idempotent replay keyed by client-provided idempotency key.
- Prefer unique workflow IDs plus optional explicit idempotency key.
- Add execution idempotency for tool calls so retries do not duplicate mutations.

**Validation**

- Unit test: two identical prompts create distinct workflows unless same idempotency key is supplied.
- Unit test: retry with same idempotency key returns same workflow.
- Unit test: execution retry does not duplicate downstream mutation.
- Live browser validation:
  - Send same high-risk prompt twice.
  - Confirm UI shows either two clearly separate workflows or explicit replay behavior.

## Independent whole-codebase review synthesis

Four independent review agents inspected the dirty worktree on 2026-05-11 against the target state:
reusable, modular, seamless, well-architected service boundaries with production-grade abstraction
layers. These findings supersede older optimistic status wording where they conflict with enterprise
readiness. The existing implementation remains a useful POC, but these items should be treated as
porting blockers or consolidation work before copying patterns into an enterprise codebase.

### Review P0 — Enterprise correctness and security blockers

- Separate OAuth scopes from workflow/resource grant scopes. Agent Service currently unions workflow
  grant scopes with Auth0 OBO request scopes, and egress compares grant-required workflow scopes
  against returned OAuth token scopes. Target state: keep `oauth_scopes` and
  `workflow_grant_scopes` as distinct typed fields, request only explicitly mapped IdP scopes, and
  reject returned token scope/audience drift.
- Replace raw bearer containment with an opaque broker/vault boundary. The Auth0 callback currently
  materializes the access token as `authContextRef`, and Agent Service token context persists bearer
  material by reference. Target state: app services hold only opaque token references; a broker or
  encrypted vault owns subject-token material, TTL, revocation, and exchange.
- Enforce MCP authorization at the MCP service boundary. Network/Cloud MCP tools attach workflow
  metadata but do not apply FastMCP/JWT/JWKS/tool-scope enforcement. Egress checks are necessary but
  not sufficient; MCPs must fail closed independently and network policy should allow only egress to
  reach them.

### Review P1 — Boundary durability and race conditions

- Replace the frontend process-local session `Map` with durable server-side session storage and TTL.
  The browser cookie now correctly stores a handle, but that handle is not valid across Next.js
  restarts, multiple workers, serverless isolates, or horizontal replicas.
- Make workflow state transitions atomic. Approval checks and execution status updates currently use
  blind store writes; use CAS/versioned transitions for `awaiting_approval -> executing ->
  completed/failed` and add idempotency keys per approval/step.
- Stop deriving workflow ids from an underspecified hash. Current IDs omit arguments, thread id, and
  run id. Use generated workflow ids or hash the canonical plan including arguments; keep replay
  idempotency as an explicit separate contract.
- Decide and implement execution semantics for non-HITL `ready` workflows. Today they can be planned
  and shown as tool calls without automatic read-only execution.
- Split internal service signing. The shared HMAC context is coarse-grained, lacks replay protection,
  and reuses one secret across trust domains. Target state: per-service asymmetric signing or mTLS,
  recipient/audience claims, key ids, nonce replay tracking, and separate keys for session context and
  execution grants.
- Keep internal services internal. Compose currently publishes control-plane services, Redis, and
  observability endpoints to the host. Target state: one public frontend ingress and private service
  networking for Agent Service, AG-UI, egress, MCPs, Redis, and telemetry.
- Fix clean-machine container builds. Python services use `FROM python-base`, but Compose does not
  build/tag that base image as part of the documented path.

### Review P2 — Modularity and reusable abstraction layers

- Split `services/agent_service/agent_service/app.py` into route adapters, workflow application
  service, runtime streaming adapter, token-exchange provider, egress client, message/thread
  projection, and redaction helpers.
- Make `session_state`, `workflow_core`, `token_broker`, and `mcp_runtime` true reusable package
  owners, or remove unused duplicated abstractions. Current state contracts and token exchange logic
  are still partially duplicated in Agent Service.
- Replace hard-coded executable tool exposure with a registry that distinguishes active executable
  tools from sample/persona metadata tools.
- Consolidate redaction lists into one normalized utility shared by frontend server routes, AG-UI,
  Agent Service, egress, and observability.
- Remove workflow-control recovery from assistant prose parsing. Workflow ids and approval state
  should flow only through typed AG-UI state/custom events and Agent Service thread state.
- Split `assistant-drawer.tsx` into thread shell, message list, composer, workflow approval, and
  workflow/tool-summary modules. Gate composer submission behind a single `assistantReady` contract.
- Add at least one frontend integration test using the real assistant-ui/AG-UI packages against a mock
  SSE route; current Vitest stubs do not prove event mapping, streaming, thread switching, or approval
  rendering.
- Refresh K8s manifests for the vNext topology or mark them explicitly stale. Current manifests do
  not deploy the active frontend, AG-UI, Agent Service, egress, Redis, Network/Cloud MCP topology.

## Remaining implementation order

1. Review P0: separate OAuth scopes from workflow grants, replace raw bearer storage with an opaque
   broker/vault boundary, and enforce MCP auth at the MCP boundary.
2. Review P1: durable frontend session storage, atomic workflow transitions, generated workflow ids,
   and explicit non-HITL execution semantics.
3. P1-2: replace the direct Auth0 OBO client with a generic enterprise token-broker seam.
4. P1-8: split streamed assistant narration from final structured `tool_intents`.
5. P1-5 and P1-1: consolidate canonical workflow/thread/session contracts now that Agent Service owns runtime state.
6. P1-4 and P2-3: externalize approval queue/event-stream durability and production session storage.
7. P2-4: replace hard-coded MCP target routing with a config-driven executable MCP registry.
8. Review P2: split Agent Service and assistant drawer into smaller application/presentation modules.
9. P2-2: complete lifecycle telemetry coverage and durable audit export.
10. P2-6: design workflow/execution idempotency with the enterprise queue/store.
11. P2-1 and P2-5: add SQL-backed long-term memory and PingFederate-specific token exchange after the enterprise boundaries are known.

## Consolidated remediation inventory from TODO.md

The former `TODO.md` remediation items are captured here so future remediation work has one source
of truth.

### Security and authorization carry-forward

- Least-privilege OBO scope exchange: request only scopes covered by the human-approved manifest, or
  introduce an explicit mapping from workflow scopes to Auth0/PingFederate API permissions and verify
  the returned token is not broader than approval.
- Unknown tool authorization must stay fail-closed across Agent Service, egress, and MCP boundaries.
- Network/Cloud MCP WRITE and ADMIN operations need equivalent downstream scope enforcement, either
  at MCP tool auth or at egress with JWT audience/scope validation.

### Protocol and UX carry-forward

- Any remaining SSE parser must be real and line-oriented, covering CRLF, comments, no-space fields,
  multiline `data:`, chunk boundaries, non-2xx responses, and timeout behavior.
- Workflow step rendering must tolerate malformed payloads without parsing raw `input_payload_json`
  directly during React render.
- The primary approval UI should hide workflow ids, plan hashes, step ids, and raw payload JSON. Render
  typed workflow/tool summaries, human-readable policy descriptions, required scopes, and approve/reject
  controls instead.

### Runtime and test hardening carry-forward

- Failed downstream MCP calls should leave workflow status `failed`; egress transport failures already
  return non-2xx and should remain covered by tests.
- Egress contract tests should use active Network/Cloud MCP targets instead of legacy identity/developer
  fixture assumptions.
- The `python-base` Docker image build path should be wired or documented so a clean machine can build
  the full Compose topology.
- Add negative tests for direct gateway auth bypass, wrong-user workflow reads/approvals, insufficient
  MCP scopes, failed downstream execution, and wrong audience.

## Validation baseline for every major refactor

After each task, run a minimum validation suite:

- Unit tests for modified modules.
- Type/lint checks if configured.
- Docker Compose startup.
- End-to-end browser flow:
  1. login
  2. send low-risk prompt
  3. receive AG-UI streamed response
  4. send high-risk prompt
  5. see approval request
  6. approve as initiating user
  7. confirm egress execution
  8. inspect audit/correlation output
- Negative authorization checks:
  - forged user
  - forged tenant
  - expired approval
  - modified tool arguments
  - insufficient scope
  - wrong audience
