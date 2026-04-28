# Auth0 Workflow Frontend

This sample app models Auth0 Client Credentials configuration and uses assistant-ui to drive
the supervisor workflow.

The app stores only non-secret Auth0 configuration in localStorage. The client secret is kept
in memory and is never written to localStorage by the sample.

Supervisor API calls are routed through a small shared client helper in `lib/server/supervisor`.
All token exchange, planning, and approval calls go to the configured supervisor endpoint; there
is no frontend mock workflow branch.

## Run Locally

```bash
npm install
npm run dev
```

Set `SUPERVISOR_BASE_URL` when using a non-default supervisor endpoint:

```bash
SUPERVISOR_BASE_URL=http://127.0.0.1:8080 npm run dev
```

## Tests

```bash
npm test
npm run lint
npm run build
npm run test:e2e
```

`npm run test:e2e` exercises the real supervisor/Auth0 flow. It requires `AUTH0_CLIENT_ID`,
`AUTH0_CLIENT_SECRET`, and `AUTH0_AUDIENCE` in the environment or root `.env`.
