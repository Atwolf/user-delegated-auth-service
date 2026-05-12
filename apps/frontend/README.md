# Auth0 Workflow Frontend

This sample app models Auth0 user-scoped Universal Login and uses assistant-ui's AG-UI runtime
to drive the Agent Service through the AG-UI gateway.

The app reads user-login Auth0 configuration from environment variables and redirects
unauthenticated users to Universal Login before rendering the assistant UI. Browser auth
interaction is limited to SSO, session state, and logout; it does not ask users for client IDs,
client secrets, token endpoints, JWKS endpoints, raw tokens, or passwords.

Supervisor and Agent Service calls are routed through the server-only helper in
`lib/server/supervisor`. The Auth0 callback validates ID/access tokens, registers server-only
token context with Agent Service, stores a signed httpOnly session cookie without that context,
and passes only sanitized session context across browser-visible boundaries. There is no
frontend mock workflow branch.

Runtime boundaries:

- `/api/ag-ui` is the browser chat/run boundary and proxies AG-UI SSE to the gateway.
- `/api/threads` creates Agent Service thread state for the active session.
- `/api/threads/[threadId]` restores thread state for the active session.
- `/api/workflows/[workflowId]` restores workflow approval context.
- `/api/workflows/[workflowId]/approve` submits approve/reject decisions to Agent Service.
- Auth interaction stays under `/api/auth/*`.

## Run Locally

```bash
npm install
npm run dev
```

Set `SUPERVISOR_BASE_URL` when using a non-default supervisor endpoint:

```bash
SUPERVISOR_BASE_URL=http://127.0.0.1:8080 npm run dev
```

Set `AG_UI_GATEWAY_URL` and `AGENT_SERVICE_URL` when the gateway or Agent Service are not on
their local defaults:

```bash
AG_UI_GATEWAY_URL=http://127.0.0.1:8088/agent AGENT_SERVICE_URL=http://127.0.0.1:8090 npm run dev
```

Required Auth0 user-login settings are `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`,
`AUTH0_USER_CLIENT_ID`, `AUTH0_APP_BASE_URL`, `AUTH0_CALLBACK_URL`, and
`AUTH0_SESSION_SECRET`. `INTERNAL_SERVICE_AUTH_SECRET` must be set separately for signed
service-to-service calls. Keep real tenant values and secrets in ignored `.env` files.

## Tests

```bash
npm test
npm run lint
npm run build
npm run test:e2e
```

`npm run test:e2e` exercises the real supervisor/Auth0 user login flow through Universal Login.
It requires Auth0 tenant config plus a sample user email and password in the environment or root
`.env`.
