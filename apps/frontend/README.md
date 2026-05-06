# Auth0 Workflow Frontend

This sample app models Auth0 user-scoped Universal Login and uses assistant-ui to drive the
supervisor workflow.

The app reads user-login Auth0 configuration from environment variables and renders only login,
session state, and logout controls. It does not ask users for client IDs, client secrets, token
endpoints, JWKS endpoints, raw tokens, or passwords.

Supervisor API calls are routed through a small shared client helper in `lib/server/supervisor`.
The Auth0 callback validates ID/access tokens, stores a signed httpOnly session cookie, and
passes only a sanitized session context to the supervisor. There is no frontend mock workflow
branch.

## Run Locally

```bash
npm install
npm run dev
```

Set `SUPERVISOR_BASE_URL` when using a non-default supervisor endpoint:

```bash
SUPERVISOR_BASE_URL=http://127.0.0.1:8080 npm run dev
```

Required Auth0 user-login settings are `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`,
`AUTH0_USER_CLIENT_ID`, `AUTH0_APP_BASE_URL`, `AUTH0_CALLBACK_URL`, and
`AUTH0_SESSION_SECRET`. Keep real tenant values and secrets in ignored `.env` files.

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
