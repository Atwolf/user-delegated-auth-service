# Auth0 Assistant UI Workflow Sample

## Purpose

The sample frontend in `apps/frontend` demonstrates an Auth0 user-scoped identity flow that
gates the assistant UI before first render and drives the AG-UI gateway through an
authenticated Next.js proxy. It is a sample UI, not production auth middleware.

## Frontend

- Next.js, TypeScript, Tailwind, MUI, assistant-ui, and the assistant-ui AG-UI runtime.
- `AssistantRuntimeProvider` wraps the app.
- The assistant is a persistent MUI drawer backed by assistant-ui primitives, MUI controls, and
  lucide icons.
- `useAgUiRuntime` uses `HttpAgent({ url: "/api/ag-ui" })`.
- `/api/ag-ui` is the authenticated Next.js proxy for AG-UI clients. It reads the signed
  session cookie, strips sensitive payload keys, injects only sanitized session context, and
  forwards to `ag_ui_gateway`.
- `/api/threads` and `/api/threads/{thread_id}` create and restore Agent Service thread state
  for the active Auth0 user/session.
- `/api/workflows/{workflow_id}` and `/api/workflows/{workflow_id}/approve` restore workflow
  context and submit approve/reject decisions through Agent Service.
- The target VM topology exposes `ag_ui_gateway` at `/agent` as the AG-UI-only HTTP/SSE
  transport boundary.
- The root page redirects unauthenticated users to `/api/auth/login`; the assistant drawer is
  not accessible before SSO succeeds.
- After login, the drawer renders only session state and logout controls for auth interaction.
- Auth0 user-login configuration comes from environment variables:
  `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `AUTH0_USER_CLIENT_ID`, `AUTH0_USER_SCOPE`,
  `AUTH0_APP_BASE_URL`, `AUTH0_CALLBACK_URL`, and `AUTH0_SESSION_SECRET`.
- Browser login uses Auth0 Authorization Code + PKCE and stores only a signed httpOnly session
  cookie. The browser does not hold client secrets, passwords, raw access tokens, ID tokens,
  refresh tokens, or authorization headers.
- After login, the assistant drawer empty state renders a persona-aware welcome from the
  server-returned `Auth0UserSession.persona`. The browser receives only a token reference,
  scopes, tool allow-list, user identity, and persona summary.

## Runtime APIs

- `POST /identity/auth0/session`
- Agent Service `POST /threads`
- Agent Service `GET /threads/{thread_id}`
- Agent Service `POST /runs/stream`
- Agent Service `POST /workflows/plan`
- Agent Service `GET /workflows/{workflow_id}`
- Agent Service `POST /workflows/{workflow_id}/approve`

`POST /identity/auth0/session` accepts only a validated user session context from the Next.js
callback boundary. It is the only remaining supervisor API in the active browser workflow:

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
`app_metadata.magnum_opus.allowed_scopes` and `allowed_mcp_tools` reads. Both metadata lists are
required and non-empty for a user session to materialize.

The supervisor emits Auth0/session traces and logs to the observability sidecar for:

- `frontend.auth0_user_login_succeeded`
- `identity.auth0_user_session_materialized`
- `on_login`

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
- The supervisor fetches the Auth0 user's `app_metadata.magnum_opus` and returns only
  browser-safe scope, tool allow-list, token reference, identity, and persona metadata.
- Agent Service consumes the sanitized session context, filters tool intents through
  `allowed_mcp_tools`, and materializes configured MCP scopes into workflow plans.
- The raw user token is not exposed to browser state or supervisor planning.
- Session/workflow persistence reuses canonical workflow models from `workflow_core`, so stored
  workflow snapshots match the manifest shape returned by Agent Service APIs.
- Frontend supervisor calls use one shared POST helper for JSON requests, `no-store` fetches,
  and consistent HTTP error messages.
- The target Agent Service emits assistant narration and `ToolIntent` records from the Google
  ADK coordinator runtime. Workflow policy derives HITL decisions from operation type, blast
  radius, scope materialization, and human-readable tool metadata before egress execution.
- The Agent Service stores sessions, token references, workflows, and AG-UI threads with
  tenant/user/session-scoped keys. Redis is required for the reference runtime; process-local
  memory is reserved for explicitly injected tests behind a test-only flag.
- The Agent Service owns the model-provider boundary behind Google ADK. `ANTHROPIC_API_KEY`
  and `ANTHROPIC_MODEL` configure ADK's direct Claude adapter; the local default is
  `claude-haiku-4-5-20251001`. Missing or disabled ADK runtime configuration fails the run;
  there is no keyword-routing compatibility path. The coordinator receives sanitized
  `tool_contracts` in the prompt and does not register ADK function tools, keeping real tool
  execution behind Agent Service dispatch. Slow or empty ADK responses surface as run errors
  instead of silent empty turns.
- The AG-UI gateway emits AG-UI SSE events for run lifecycle, assistant text, state deltas, tool
  calls, custom HITL approval requests, run completion, and run errors.

## Approval UI Contract

Approval surfaces should render workflow policy and tool intent in user-facing terms:

- Use `policy.human_description`, required scopes, tool names, and typed tool arguments as the
  primary approval content.
- Treat workflow ids, plan hashes, step ids, and raw `input_payload_json` as routing or
  diagnostic fields.
- Submit only `approved` and `plan_hash` from the browser; the Next.js route derives
  user/session identity from the signed Auth0 session cookie before delegating to Agent
  Service.

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
   - `headline` and `greeting` from metadata overrides or browser-safe derived text.
7. The supervisor emits `on_login` with non-secret persona attributes.
8. The frontend maps the response to `Auth0UserSession.persona`, registers the server-only
   Auth0 token context with Agent Service, stores only the browser-safe session cookie, and
   renders the assistant welcome before the first workflow request.

The frontend does not store raw JWTs, prompt for OAuth endpoints, or use persona fields for
authorization decisions.

## Local Compose Verification

Run:

```bash
docker compose --env-file .env -f infra/docker/docker-compose.yaml up --build -d
```

Open:

- Frontend: `http://127.0.0.1:3000`
- Supervisor: `http://127.0.0.1:8080`
- AG-UI gateway: `http://127.0.0.1:8088/agent`
- Agent Service: `http://127.0.0.1:8090`
- Egress Gateway: `http://127.0.0.1:8091`
- Sidecar telemetry: `http://127.0.0.1:4319/v1/telemetry`

The Compose stack uses the configured Auth0 tenant. It does not include a mock identity
provider. It includes Redis, POC Network/Cloud MCP services, the AG-UI gateway, the Google
ADK-backed Agent Service, and Redis-backed Agent Service state without process-local rescue. Durable
workflow execution hardening remains future work.

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
UV_CACHE_DIR=/tmp/uv-cache uv run --locked pytest
UV_CACHE_DIR=/tmp/uv-cache uv run --locked ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run --locked mypy .
UV_CACHE_DIR=/tmp/uv-cache uv run --locked pyright
cd apps/frontend
npm test
npm run lint
npm run build
```

Docker integration:

1. `docker compose --env-file .env -f infra/docker/docker-compose.yaml up --build -d`.
2. Verify services are healthy.
3. Run a direct Auth0 metadata smoke test against supervisor
   `POST /identity/auth0/session`, then plan, restore, approve, and complete the workflow
   through Agent Service APIs. Assert `allowed_mcp_tools` filters actions and dynamic scopes
   include `read:client:sample-app` and `read:user:sample-user`.

Playwright E2E:

1. Run `npm run test:e2e` from `apps/frontend` with real Auth0 env available.
2. Assert unauthenticated `/` immediately redirects to Auth0 Universal Login and does not render
   the assistant drawer or any OIDC Client ID, Client Secret, token endpoint, JWKS endpoint,
   password, or raw token fields.
3. Complete Universal Login with the sample user, return logged in, send
   `Check user sample-user and app sample-app`, assert the approval card and dynamic scopes,
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
