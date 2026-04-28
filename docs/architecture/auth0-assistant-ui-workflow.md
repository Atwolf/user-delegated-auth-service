# Auth0 Assistant UI Workflow Sample

## Purpose

The sample frontend in `apps/frontend` demonstrates an Auth0 Client Credentials identity flow
driving the supervisor plan-authorize-execute workflow. It is a sample UI, not production auth
middleware.

## Frontend

- Next.js, TypeScript, Tailwind, assistant-ui, and AI SDK v6.
- `AssistantRuntimeProvider` wraps the app.
- The full-page chat uses a local `Thread` component backed by assistant-ui primitives.
- The floating chat widget uses `AssistantModal`.
- `useChatRuntime` uses `AssistantChatTransport({ api: "/api/chat" })`.
- The Auth0 configuration panel persists only non-secret fields to localStorage.
- Client secret remains in React state and is sent only to the Next.js API route for the
  sample token exchange.

## Supervisor APIs

- `POST /identity/client-credentials/token`
- `POST /workflows/plan`
- `POST /workflows/{workflow_id}/approve`
- `GET /workflows/{workflow_id}`

The supervisor emits both traces and logs to the observability sidecar for:

- `frontend.auth0_config_submitted`
- `identity.client_credentials_token_exchanged`
- `workflow.planned`
- `workflow.awaiting_approval`
- `workflow.approved`
- `workflow.step_executed`
- `workflow.completed`

Sidecar redaction covers client secrets, access tokens, authorization headers, and token-like
fields before telemetry is stored or returned.

## Shared Workflow Runtime

- MCP services use the shared `mcp_runtime` package for FastMCP imports, Auth0-compatible
  runtime scope checks, and workflow authorization metadata.
- Sample tool authorization metadata is centralized in `workflow_core.tool_catalog`; the
  supervisor adapts required workflow scopes to the scopes actually returned by Auth0.
- The token broker prefers Auth0's top-level `scope` response and falls back to the access
  token's `scope` or `permissions` claims before using requested scopes.
- Session/workflow persistence reuses canonical workflow models from `workflow_core`, so stored
  workflow snapshots match the manifest shape returned by supervisor APIs.
- Frontend supervisor calls use one shared POST helper for JSON requests, `no-store` fetches,
  and consistent HTTP error messages.

## Local Compose Verification

Run:

```bash
docker compose -f infra/docker/docker-compose.yaml up --build -d
```

Open:

- Frontend: `http://127.0.0.1:3000`
- Supervisor: `http://127.0.0.1:8080`
- Sidecar telemetry: `http://127.0.0.1:4319/v1/telemetry`

The Compose stack uses the configured Auth0 token endpoint. It does not include a mock identity
provider. It also omits the unused Temporal placeholder; durable Temporal-backed workflow
execution remains future work.

For real Auth0 Client Credentials exchanges, `audience` must be set to an Auth0 API Identifier
unless the tenant has a default audience configured. A missing audience returns Auth0
`access_denied` with HTTP 403 before workflow planning can proceed.

## Verification Gates

Backend:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run mypy .
UV_CACHE_DIR=/tmp/uv-cache uv run pyright
```

Frontend:

```bash
cd apps/frontend
npm test
npm run lint
npm run build
npm run test:e2e
```
