# Agent Service Architecture

The service is organized around Pydantic v2 contracts:

- `a2a_runtime` validates inter-agent envelopes and typed payloads.
- `workflow_core` owns workflow plans, steps, authorization bundles, scope materialization, and
  deterministic plan hashing.
- `agent_runtime` owns invocation context and protocol interfaces.
- `session_state` owns Redis-backed session/workflow state contracts.
- `token_broker` owns OBO token exchange request/response contracts.
- `observability` owns redaction-safe event emission helpers.
- `observability_sidecar` receives agentic traces and log payloads over HTTP, redacts
  sensitive fields, and exposes bounded recent telemetry for tests and local monitoring.
- `apps/frontend` is a standalone Next.js assistant-ui sample for Auth0 Client Credentials
  workflow approval.
- `identity_provider_mock` is a local Auth0-compatible Client Credentials issuer used by
  Compose and integration verification.

Runtime flow:

1. Supervisor receives a user request.
2. Supervisor discovers enabled subagents from mounted SQLite.
3. Supervisor asks each subagent for a typed tool proposal.
4. Workflow core builds a plan, derives scopes from MCP metadata, deduplicates them, and hashes
   the canonical plan JSON.
5. The sample frontend exchanges Auth0 Client Credentials through
   `POST /identity/client-credentials/token`; secrets are memory-only or environment-backed
   and are not persisted by the browser sample.
6. The supervisor stores the manifest in sample in-memory workflow state and returns an
   awaiting-approval record to the frontend.
7. `POST /workflows/{workflow_id}/approve` records the human approval and executes approved
   steps deterministically in manifest order.
8. Services post agentic traces to `/v1/traces` and logs to `/v1/logs` on the
   observability sidecar. Tests and operators can inspect `/v1/stats`, `/v1/telemetry`,
   `/v1/monitor/components`, and `/v1/monitor/event-types`.

The current implementation remains a local scaffold: workflow execution is deterministic and
sample-oriented, while durable Temporal-backed execution remains future work.
