> Historical implementation prompt. This file records the original VM-first implementation
> guidance. Current runtime boundaries are documented in `docs/architecture/agent-service.md`
> and `docs/architecture/auth0-assistant-ui-workflow.md`; those docs supersede this prompt for
> the vNext assistant-ui AG-UI, Agent Service, Redis-backed state, and Chainlit removal
> decisions.

## Primary implementation language

Use **Python** as the primary implementation language.

Use **Pydantic v2** for typed data contracts, validation, serialization, and boundary enforcement.

Use Python typing throughout:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
```

Do not use untyped dictionaries for core workflow, session, token, MCP, or AG-UI contracts
except at the outermost unknown payload boundary.

Use Pydantic models for:

* workflow plans
* workflow steps
* approved workflows
* Redis session/workflow state records
* workflow events
* token broker requests/responses
* OpenTelemetry event attribute payloads
* agent request/response bodies

Use `Protocol` interfaces for component abstractions, such as:

* `SessionStateStore`
* `TokenBrokerClient`
* `WorkflowEventEmitter`
* `ToolIntentProvider`

---

## Historical resolved implementation decisions

These defaults were used for the original implementation prompt. For vNext, apply these only
where current architecture docs do not conflict:

1. **Pydantic version:** Pydantic v2.
2. **Agent runtime framework:** Google ADK behind the Agent Service boundary.
3. **Concurrency model:** fully async implementation.
4. **HTTP client:** `httpx.AsyncClient` is approved.
5. **Redis client:** `redis.asyncio` is approved; include a Redis layer in Compose.
6. **Package/dependency manager:** `uv`.
7. **Type checking:** run both `mypy` and `pyright`.
8. **Linting/formatting:** `ruff`.
9. **Container build strategy:** shared Python base image for service containers.
10. **Shared package install mode (dev):** editable local packages.
11. **Runtime payload typing:** strict typed payloads per action.
12. **Redis representation:** use Pydantic JSON blobs by default; use Redis-native structures only when they materially improve access patterns. Evaluate LangChain cache adapters if useful.
13. **Workflow event buffering:** use Redis-backed buffering in addition to OTEL emission.
14. **Workflow state durability:** use Agent Service persistence with Redis and process-local fallback for POC mode.
15. **OBO token responses:** keep raw access tokens server-side.

---

## New mandatory implementation requirements

### 1) Supervisor subagent discovery via mounted persistent database (SQLite)

The supervisor must discover available subagents dynamically from a mounted SQLite database.

**Requirements**

* Use SQLite as persistent storage (`sqlite3`/`aiosqlite`) with a mounted volume.
* Add a `subagents` table and load enabled entries at startup and on refresh.
* Each subagent record must include at least:
  * `agent_name` (unique)
  * `base_url`
  * `mcp_server_name`
  * `enabled`
  * `priority`
  * `updated_at`
* Supervisor discovery service must be async and return typed Pydantic records.

Example schema:

```sql
CREATE TABLE IF NOT EXISTS subagents (
  agent_name TEXT PRIMARY KEY,
  base_url TEXT NOT NULL,
  mcp_server_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 100,
  updated_at TEXT NOT NULL
);
```

### 2) MCP isolation model: one MCP per subagent pod

Implement several MCP servers, each isolated in its own pod/container boundary.

**Requirements**

* Each subagent has exactly one unique MCP configuration.
* Do not share MCP process instances across subagents.
* Each MCP must expose only the tools/resources relevant to that subagent.
* Service routing should prevent direct external ingress to subagent MCP ports unless explicitly needed.
* Supervisor routes A2A/MCP calls internally.

### 3) Workflow protocol: plan -> authorize -> execute

When supervisor receives a user query:

1. Discover active subagents from SQLite.
2. Ask each subagent “what can you do for this request?”
3. Each subagent returns a **proposed tool call** and **arguments** (typed model).
4. Build workflow plan from these proposals.
5. Collect required scopes from tool metadata.
6. Perform token exchange using deduplicated scopes (e.g. `['DOE.Developer.ABCD']`).
7. Await/perform authorization gate.
8. Execute approved workflow steps.

All messages and states in this sequence must be Pydantic-validated.

---

## FastMCP integration requirements (based on latest FastMCP patterns)

Use FastMCP tool decorators and authorization checks (`auth=require_scopes(...)`) and add custom metadata needed for HITL and scope derivation.

### Restricted-tool decorator contract

Every MCP tool participating in workflow authorization must declare:

* scope template(s)
* scope argument mapping fields
* operation (`READ`/`WRITE`/...)
* HITL description

Preferred contract:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from fastmcp.server.auth import require_scopes

P = ParamSpec("P")
R = TypeVar("R")


def restricted(
    *,
    scopes: str | list[str],
    args: str | list[str] | None,
    op: str,
    hitl: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Attach declarative auth metadata used by plan->authorize->execute."""

    declared_scopes = [scopes] if isinstance(scopes, str) else scopes
    declared_args = [args] if isinstance(args, str) else (args or [])

    def _decorator(fn: Callable[P, R]) -> Callable[P, R]:
        setattr(
            fn,
            "__workflow_authz__",
            {
                "scopes": declared_scopes,
                "scope_args": declared_args,
                "op": op,
                "hitl": hitl,
            },
        )
        return fn

    return _decorator
```

Usage with FastMCP:

```python
from fastmcp import FastMCP
from fastmcp.server.auth import require_scopes

mcp = FastMCP("developer-mcp")


@restricted(
    scopes="DOE.Developer.{appid}",
    args="appid",
    op="READ",
    hitl="Read developer app metadata for selected app ID",
)
@mcp.tool(
    name="get_developer_app",
    auth=require_scopes("DOE.Developer.read"),
    tags={"developer", "read"},
)
async def get_developer_app(appid: str) -> dict[str, Any]:
    return {"appid": appid}
```

> Notes:
>
> * FastMCP supports decorator-based tool registration and component auth checks.
> * Keep workflow-specific metadata on the function (`__workflow_authz__` or equivalent) so supervisor can derive runtime scopes.

### Scope materialization

The supervisor must materialize scope templates from declared arg names and actual tool arguments.

Example:

* template: `DOE.Developer.{appid}`
* args: `{ "appid": "ABCD" }`
* materialized scope: `DOE.Developer.ABCD`

Deduplicate and sort scopes before token exchange.

---

## Python package layout

Adapt to existing repository structure first. If no structure exists, prefer:

```text
/
  pyproject.toml
  uv.lock

  services/
    supervisor/
      agent_service_supervisor/
        __init__.py
        app.py
        config.py
        routes.py
      tests/

    ag_ui_gateway/
      ag_ui_gateway/
        __init__.py
        app.py
        client.py
        models.py
        sse.py
      tests/

    agent_service/
      agent_service/
        __init__.py
        app.py
        models.py
        orchestration.py
        providers.py
        state.py
      tests/

    egress_gateway/
      egress_gateway/
        __init__.py
        app.py
      tests/

    mcps/
      network_mcp/
        network_mcp/
          __init__.py
          server.py
          tools.py
        tests/

      cloud_mcp/
        cloud_mcp/
          __init__.py
          server.py
          tools.py
        tests/

    observability_sidecar/
      observability_sidecar/
        __init__.py
        app.py
      tests/

  packages/
    workflow_core/
      workflow_core/
        __init__.py
        models.py
        hashing.py
        authz.py
        executor_contracts.py
        idempotency.py
      tests/

    session_state/
      session_state/
        __init__.py
        models.py
        redis_store.py
        key_builder.py
        interfaces.py
      tests/

    token_broker/
      token_broker/
        __init__.py
        models.py
        client.py
        interfaces.py
        mock.py
      tests/

    observability/
      observability/
        __init__.py
        models.py
        otel.py
        redaction.py
        events.py
      tests/

    mcp_runtime/
      mcp_runtime/
        __init__.py
        auth.py
        decorators.py
        fastmcp.py
      tests/

  infra/
    docker/
      docker-compose.yaml
    k8s/
      agent-service/
        deployment.yaml
        service.yaml
        configmap.yaml
        secrets.example.yaml

  docs/
    adr/
      0001-agent-service-multicontainer-pod.md
    architecture/
      agent-service.md

  tests/
    integration/
```

---

## Runtime and framework guidance

1. Inspect the repo before introducing frameworks.
2. Browser chat traffic should enter through assistant-ui's AG-UI runtime and the AG-UI gateway.
3. Agent Service owns the Coordinator/Dispatcher boundary and should use Google ADK when model
   runtime configuration is present.
4. Expose service boundaries via FastAPI.
5. Use one lifecycle-managed `httpx.AsyncClient` per process for outbound service calls.
6. Add dependencies incrementally.

Recommended toolchain:

* Agent runtime: Google ADK coordinator behind Agent Service
* Browser runtime: assistant-ui AG-UI `HttpAgent`
* HTTP server shell: FastAPI
* Pydantic: v2
* Redis client: `redis.asyncio`
* Tests: `pytest`, `pytest-asyncio`
* Type checks: `mypy` + `pyright`
* Lint/format: `ruff`
* Package management: `uv`

---

## Pydantic model contracts

Use the following shapes as semantic baselines and rename only to match repo conventions.

### Subagent discovery model

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubagentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    mcp_server_name: str = Field(..., min_length=1)
    enabled: bool = True
    priority: int = Field(default=100)
    updated_at: datetime
```

### Tool proposal and workflow authz models

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    reason: str | None = None


class ScopeRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_template: str = Field(..., min_length=1)
    scope_args: list[str] = Field(default_factory=list)
    op: str = Field(..., min_length=1)
    hitl_description: str = Field(..., min_length=1)


class AuthorizationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    scopes: list[str] = Field(default_factory=list)
    proposals: list[ToolProposal] = Field(default_factory=list)
```

### Runtime request context

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RuntimeRequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str | None = None

    agentic_span_id: str = Field(..., min_length=1)
    parent_agentic_span_id: str | None = None
    trace_id: str | None = None

    thread_id: str | None = None

    plan_hash: str | None = None
    approval_id: str | None = None
    step_id: str | None = None

    token_ref: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)

    idempotency_key: str = Field(..., min_length=1)
```

### Workflow models

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(..., min_length=1)
    target_agent: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    input_model_type: str = Field(..., min_length=1)
    input_payload_json: str = Field(..., min_length=2)

    required_scopes: list[str] = Field(default_factory=list)
    downstream_audience: str | None = None
    mutates_external_state: bool = False


class WorkflowPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    steps: list[WorkflowStep]


class ApprovedWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    approval_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)

    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by_user_id: str = Field(..., min_length=1)

    approved_scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class WorkflowStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "created",
        "planned",
        "awaiting_approval",
        "approved",
        "executing",
        "completed",
        "failed",
        "cancelled",
    ] = "created"
```

### Session state models

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SessionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)

    auth_context_ref: str = Field(..., min_length=1)
    active_workflow_id: str | None = None

    version: int = Field(default=0, ge=0)
    values: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str = Field(..., min_length=1)

    plan: WorkflowPlan | None = None
    approved_workflow: ApprovedWorkflow | None = None
    status: WorkflowStatus

    version: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### Workflow event model

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str | None = None
    step_id: str | None = None

    agent_name: str | None = None
    agentic_span_id: str = Field(..., min_length=1)
    parent_agentic_span_id: str | None = None
    trace_id: str | None = None

    plan_hash: str | None = None
    approval_id: str | None = None
    idempotency_key: str | None = None

    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### Token broker models

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkflowTokenExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str = Field(..., min_length=1)
    approval_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)

    tenant_id: str | None = None
    auth_context_ref: str = Field(..., min_length=1)

    requested_scopes: list[str] = Field(default_factory=list)
    requested_audience: str | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)


class WorkflowTokenExchangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(..., min_length=1)
    expires_at: datetime
    scopes: list[str] = Field(default_factory=list)
    audience: str | None = None
```

---

## Python interfaces

Current vNext interfaces are service-boundary specific:

* Agent Service model-provider contracts live in `services/agent_service/agent_service/providers.py`.
* Agent Service persistence contracts live in `services/agent_service/agent_service/state.py`.
* Workflow/tool authorization contracts live in `packages/workflow_core/workflow_core/`.
* Browser-safe session state contracts live in `packages/session_state/session_state/`.
* OBO exchange contracts live in `packages/token_broker/token_broker/`.
* MCP runtime auth/decorator contracts live in `packages/mcp_runtime/mcp_runtime/`.

Do not recreate the removed A2A envelope layer or standalone `agent_runtime` package unless the
architecture docs are updated to reintroduce that abstraction boundary.

---

## Deterministic hashing guidance

Use Pydantic serialization plus canonical JSON for deterministic workflow hashing.

```python
import hashlib
import json

from workflow_core.models import WorkflowPlan


def canonical_json(model: WorkflowPlan) -> str:
    payload = model.model_dump(mode="json", exclude_none=True, by_alias=False)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def plan_hash(plan: WorkflowPlan) -> str:
    digest = hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

Include tests proving equivalent plans produce the same hash.

---

## Deployment guidance (compose + containers)

* Use a **shared Python base image** for all service Dockerfiles.
* Add Redis in local Compose for Agent Service state.
* Keep Auth0 Management API credentials behind the supervisor service boundary.
* Use editable installs for shared local packages in development containers.

Example compose shape:

```yaml
services:
  supervisor:
    build:
      context: .
      dockerfile: services/supervisor/Dockerfile
    environment:
      - AUTH0_DOMAIN=${AUTH0_DOMAIN}
      - AUTH0_MANAGEMENT_CLIENT_ID=${AUTH0_MANAGEMENT_CLIENT_ID}
      - AUTH0_MANAGEMENT_CLIENT_SECRET=${AUTH0_MANAGEMENT_CLIENT_SECRET}
    depends_on:
      - observability-sidecar

  frontend:
    build:
      context: .
      dockerfile: apps/frontend/Dockerfile
    environment:
      - AUTH0_DOMAIN=${AUTH0_DOMAIN}
      - AUTH0_USER_CLIENT_ID=${AUTH0_USER_CLIENT_ID}
      - AUTH0_SESSION_SECRET=${AUTH0_SESSION_SECRET}
    depends_on:
      - ag-ui-gateway
      - agent-service

  ag-ui-gateway:
    build:
      context: .
      dockerfile: services/ag_ui_gateway/Dockerfile
    depends_on:
      - agent-service

  agent-service:
    build:
      context: .
      dockerfile: services/agent_service/Dockerfile
    depends_on:
      - redis
      - egress-gateway

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

---

## Redis and observability guidance

* Use `redis.asyncio` for low-latency state/cache operations.
* Prefer Pydantic JSON for portability and schema evolution.
* Use Redis for thread, workflow, session, and event buffering.
* Emit observability events via OpenTelemetry in addition to Redis-backed buffering.

---

## Logging and redaction

Use structured logging.

Never log:

* raw access tokens in plaintext logs
* authorization headers
* secrets
* full sensitive payloads

Given the requirement to use raw access tokens behind server-side boundaries, keep token lifetime
short, transport over TLS only, and ensure logs always redact token material. Do not expose raw
tokens to browser-visible state.

---

## Current implementation scope

The active implementation is no longer Python-only scaffolding. It is a POC runtime with a
Next.js assistant-ui frontend, AG-UI gateway, Agent Service, egress gateway, Network/Cloud MCP
services, Redis-backed state, and supervisor-only Auth0 metadata loading.

Scope:

```text
- Auth0 Universal Login and signed httpOnly browser session cookie
- browser-safe session DTOs without raw token context
- AG-UI HTTP/SSE browser proxy through Next.js
- Agent Service workflow planning, thread state, approval validation, OBO lookup, and egress delegation
- Network/Cloud MCP scaffolds backed by shared mcp_runtime metadata
- deterministic workflow plan hashing and scope materialization
- broad Python and frontend validation gates
- architecture docs documenting current service boundaries
```

Acceptance criteria:

```text
- Pydantic models validate required fields across service boundaries
- unauthenticated users are redirected to SSO before the assistant UI renders
- browser-visible state excludes client secrets, raw tokens, authorization headers, and token endpoints
- supervisor exposes only Auth0 metadata loading plus health
- Agent Service can plan, restore, approve, and execute workflow state through typed APIs
- workflow plan hashing is deterministic
- Python and frontend tests, lint, type checks, build, and Browser smoke tests pass locally
```

The key design is unchanged: **Pydantic models are the contract layer**, enabling independent
evolution of frontend proxies, AG-UI gateway, Agent Service, Redis/session layer, token broker,
MCP runtime, egress gateway, and observability components.

---

## Begin implementation across parallel worktrees

Use parallel worktrees immediately. The goal is independent progress with stable contract boundaries.

### Worktree plan

Create worktrees from a shared base branch and assign ownership:

```text
worktrees/
  wt-supervisor        -> supervisor API, SQLite discovery, orchestration
  wt-agent-runtime     -> agent runtime context/interfaces
  wt-workflow-core     -> workflow models, hashing, scope materialization
  wt-session-state     -> Redis state/cache models + store interfaces
  wt-token-broker      -> token exchange contracts/client scaffolding
  wt-observability     -> event models + OTEL emitter contracts
  wt-mcp-developer     -> isolated developer MCP server/tools
  wt-mcp-billing       -> isolated billing MCP server/tools
  wt-mcp-identity      -> isolated identity MCP server/tools
```

### Ownership boundaries (must not be violated)

* `wt-workflow-core` owns canonical `WorkflowPlan`, `WorkflowStep`, hash, and scope derivation utilities.
* `wt-agent-runtime` owns invocation context and cross-cutting protocols.
* `wt-session-state` owns Redis persistence contracts and key strategy.
* `wt-token-broker` owns token exchange request/response contracts.
* `wt-observability` owns event emission contracts and redaction-safe payload helpers.
* `wt-supervisor` consumes all shared packages; it does not redefine shared contracts.
* Each MCP worktree owns exactly one MCP server and its tools.

### Parallel delivery order

1. **Foundation wave (parallel):** `workflow-core`, `agent-runtime`, `token-broker`, `observability`.
2. **State + discovery wave (parallel):** `session-state`, `supervisor` SQLite discovery.
3. **MCP wave (parallel):** one isolated MCP per worktree.
4. **Integration wave:** supervisor plan->authorize->execute wiring against shared contracts.

### Integration protocol between worktrees

* Shared packages publish typed APIs first; consumers integrate only released interfaces.
* Avoid cross-worktree direct imports outside shared package boundaries.
* Rebase frequently; merge in dependency order (foundation -> state/discovery -> MCPs -> supervisor integration).
* Every merge must keep `mypy`, `pyright`, and `ruff` green for touched packages.

### Required outputs per worktree

Each worktree PR must include:

* package/module changes for its owned scope only
* unit tests for new contract validation
* brief ADR/update note if architecture decisions changed
* no breaking contract changes without coordinated version bump and migration notes

### Supervisor integration acceptance gates

Before final integration complete, verify:

* supervisor can read enabled subagents from mounted SQLite DB
* supervisor can request tool proposals from all discovered subagents
* scope templates from MCP tool metadata are materialized deterministically
* authorization bundle scopes are deduplicated and token exchange request is formed
* approved workflows execute in step order with event emission and state updates
