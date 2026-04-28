# Auth0 Workflow Frontend

This sample app models Auth0 Client Credentials configuration and uses assistant-ui to drive
the supervisor workflow.

The app stores only non-secret Auth0 configuration in localStorage. The client secret is kept
in memory and is never written to localStorage by the sample.

## Run Locally

```bash
npm install
npm run dev
```

Set `SUPERVISOR_BASE_URL` when using a non-default supervisor endpoint:

```bash
SUPERVISOR_BASE_URL=http://127.0.0.1:8080 npm run dev
```

For isolated UI testing without backend services:

```bash
SUPERVISOR_BASE_URL=mock npm run dev
```

## Tests

```bash
npm test
npm run lint
npm run build
npm run test:e2e
```
