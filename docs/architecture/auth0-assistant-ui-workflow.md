# Auth0 Assistant UI Workflow Sample

## Purpose

The sample frontend in `apps/frontend` demonstrates an Auth0 user-scoped identity flow that can
drive both the legacy supervisor workflow routes and the target AG-UI gateway. It is a sample
UI, not production auth middleware.

## Frontend

- Next.js, TypeScript, Tailwind, assistant-ui, and AI SDK v6.
- `AssistantRuntimeProvider` wraps the app.
- The full-page chat uses a local `Thread` component backed by assistant-ui primitives.
- The floating chat widget uses `AssistantModal`.
- `useChatRuntime` uses `AssistantChatTransport({ api: "/api/chat" })`.
- `/api/ag-ui` is the authenticated Next.js proxy for future AG-UI clients. It reads the signed
  session cookie, injects only sanitized session context, and forwards to `ag_ui_gateway`.
- The target VM topology also exposes `ag_ui_gateway` at `/agent` for AG-UI HTTP/SSE transport
  and `chainlit_middleware` for Chainlit Copilot-style legacy message forwarding.
- The Auth0 login panel renders only login, session state, and logout controls.
- Auth0 user-login configuration comes from environment variables:
  `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `AUTH0_USER_CLIENT_ID`, `AUTH0_USER_SCOPE`,
  `AUTH0_APP_BASE_URL`, `AUTH0_CALLBACK_URL`, and `AUTH0_SESSION_SECRET`.
- Browser login uses Auth0 Authorization Code + PKCE and stores only a signed httpOnly session
  cookie. The browser does not hold client secrets, passwords, raw access tokens, ID tokens,
  refresh tokens, or authorization headers.
- After login, the assistant thread empty state renders a persona-aware welcome from the
  server-returned `Auth0UserSession.persona`. The browser receives only a token reference,
  scopes, tool allow-list, user identity, and persona summary.

## Supervisor APIs

- `POST /identity/auth0/session`
- `POST /workflows/plan`
- `POST /workflows/{workflow_id}/approve`
- `GET /workflows/{workflow_id}`

`POST /identity/auth0/session` accepts only a validated user session context from the Next.js
callback boundary:

- Auth0 subject.
- Session ID.
- Token reference.
- User-scoped token scopes.
- Optional user email/name.

It returns:

- `token_ref`: opaque reference derived from the Auth0 access token hash.
- `scope`: the effective Auth0/user-metadata scopes that can be used for workflow planning.
- `allowed_tools`: MCP tool allow-list from `app_metadata.magnum_opus.allowed_mcp_tools`.
- `persona`: display-only assistant persona derived by the supervisor from validated session
  facts and `app_metadata.magnum_opus`.

The Management API M2M service boundary is isolated behind supervisor environment variables:
`AUTH0_MANAGEMENT_CLIENT_ID`, `AUTH0_MANAGEMENT_CLIENT_SECRET`, and
`AUTH0_MANAGEMENT_AUDIENCE`. These credentials are used only for
`app_metadata.magnum_opus.allowed_scopes` and `allowed_mcp_tools` reads.

The supervisor emits both traces and logs to the observability sidecar for:

- `frontend.auth0_user_login_succeeded`
- `identity.auth0_user_session_materialized`
- `on_login`
- `workflow.planned`
- `workflow.awaiting_approval`
- `workflow.approved`
- `workflow.execution_delegated` on the legacy supervisor approval path

Sidecar redaction covers passwords, client secrets, access tokens, authorization headers, and
token-like fields before telemetry is stored or returned.

## Shared Workflow Runtime

- MCP services use the shared `mcp_runtime` package for FastMCP imports, Auth0-compatible
  runtime scope checks, and workflow authorization metadata.
- Sample tool authorization metadata is centralized in `workflow_core.tool_catalog`; Auth0
  coarse permissions remain the runtime authorization input, while workflow scope templates
  such as `read:client:{appid}` are materialized from approved tool arguments into the manifest.
- The Next.js callback validates Auth0 ID/access tokens against JWKS, then sends only the
  sanitized session context to the supervisor.
- The supervisor fetches the Auth0 user's `app_metadata.magnum_opus`, filters proposed tools
  through `allowed_mcp_tools`, and materializes configured MCP scopes into workflow plans.
- The raw user token is not exposed to browser state or supervisor planning.
- Session/workflow persistence reuses canonical workflow models from `workflow_core`, so stored
  workflow snapshots match the manifest shape returned by supervisor APIs.
- Frontend supervisor calls use one shared POST helper for JSON requests, `no-store` fetches,
  and consistent HTTP error messages.
- The target Agent Service emits `ToolIntent` records from Network Services and Cloud
  Operations subagents. Workflow policy derives HITL decisions from operation type, blast
  radius, scope materialization, and human-readable tool metadata before egress execution.

## Login Persona Flow

The persona flow is deliberately one-way and display-only:

1. The browser navigates to `/api/auth/login`.
2. The Next.js route creates a PKCE verifier/challenge and redirects to Auth0 Universal Login.
3. `/api/auth/callback` validates state, nonce, ID token, and access token, then derives only
   `user_id`, `token_ref`, user scopes, and non-secret profile fields.
4. The callback calls `POST /identity/auth0/session`.
5. The supervisor fetches `app_metadata.magnum_opus` with the Management API M2M application.
6. The supervisor derives `UserPersona`:
   - `display_name` from metadata `display_name`, token `name`/`nickname`, email prefix, or
     subject.
   - `traits` from metadata `persona_traits` or from session facts such as email, scope count,
     and available MCP tool count.
   - `headline` and `greeting` from metadata overrides or deterministic fallback text.
7. The supervisor emits `on_login` with non-secret persona attributes.
8. The frontend maps the response to `Auth0UserSession.persona` and renders the assistant
   welcome before the first workflow request.

The frontend does not store raw JWTs, prompt for OAuth endpoints, or use persona fields for
authorization decisions.

## Local Compose Verification

Run:

```bash
docker compose -f infra/docker/docker-compose.yaml up --build -d
```

Open:

- Frontend: `http://127.0.0.1:3000`
- Supervisor: `http://127.0.0.1:8080`
- AG-UI gateway: `http://127.0.0.1:8088/agent`
- Agent Service: `http://127.0.0.1:8090`
- Egress Gateway: `http://127.0.0.1:8091`
- Chainlit middleware: `http://127.0.0.1:8092`
- Sidecar telemetry: `http://127.0.0.1:4319/v1/telemetry`

The Compose stack uses the configured Auth0 tenant. It does not include a mock identity
provider. It includes POC Network/Cloud MCP services and deterministic gateway/service
boundaries, while durable Temporal-backed workflow execution remains future work.

For real Auth0 user login, `AUTH0_AUDIENCE` must be set to an Auth0 API Identifier. The user
login application must allow the local callback/logout URLs. The supervisor's server-side
Management API M2M application must be granted `read:users` and `read:users_app_metadata` so it
can load MCP authorization metadata.

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

## Real Auth0 Handoff Procedure

Preconditions:

1. Auth0 tenant has a user-login application configured for local callback/logout URLs such as
   `http://127.0.0.1:3000/api/auth/callback`.
2. `Username-Password-Authentication` is enabled for the user-login app.
3. Auth0 API Identifier is configured as `AUTH0_AUDIENCE`.
4. Management API M2M app is separately authorized for `read:users` and
   `read:users_app_metadata`.
5. Two sample users exist with `app_metadata.magnum_opus.allowed_scopes` and
   `allowed_mcp_tools`.
6. Local ignored `.env` has real values. Do not print it.

Required automated checks:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync mypy .
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pyright
cd apps/frontend
npm test
npm run lint
npm run build
```

Docker integration:

1. `docker compose -f infra/docker/docker-compose.yaml up --build -d`.
2. Verify services are healthy.
3. Run a direct supervisor smoke test with a validated user session context: plan workflow,
   assert `allowed_mcp_tools` filters actions, assert dynamic scopes include
   `read:client:sample-app` and `read:user:sample-user`, approve workflow, and assert completed
   status.

Playwright E2E:

1. Run `npm run test:e2e` from `apps/frontend` with real Auth0 env available.
2. Assert the Auth0 panel does not contain OIDC Client ID, Client Secret, token endpoint, JWKS
   endpoint, password, or raw token fields.
3. Click `Log in with Auth0`, complete Universal Login with the sample user, return logged in,
   send `Check user sample-user and app sample-app`, assert the approval card and dynamic scopes,
   assert disallowed tools are absent, approve, and assert completed state.

Telemetry/redaction:

1. Fetch `http://127.0.0.1:4319/v1/telemetry`.
2. Confirm expected events: login succeeded/session materialized if emitted,
   `workflow.planned`, `workflow.awaiting_approval`, `workflow.approved`,
   `workflow.step_executed`, and `workflow.completed`.
3. Confirm serialized telemetry does not contain management client secrets, user passwords,
   `access_token`, `id_token`, `refresh_token`, or authorization header values.

Failure handling:

- If Auth0 returns an error, report only the exact non-secret error, HTTP status, and dashboard
  configuration needed.
- Remove Playwright test artifacts if they contain screenshots or snapshots with sensitive
  form values.
