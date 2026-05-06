# ADR 0001: Agent Service Multi-Container Boundaries

## Status

Accepted

## Context

The supervisor must preserve the Auth0/session boundary, but the target runtime needs separate
protocol, agent, egress, and MCP service boundaries. Each subagent has one unique MCP
configuration and MCP processes must not be shared across subagents.

## Decision

The implementation uses a Python monorepo with Pydantic v2 contracts as the stable boundary
between services. The supervisor remains as the Auth0 metadata and legacy workflow
compatibility surface. The target path is split into `ag_ui_gateway`, `chainlit_middleware`,
`agent_service`, and `egress_gateway` containers. The Agent Service owns deterministic
Coordinator/Dispatcher intent planning and process-local POC state. The Egress Gateway owns
outbound request primitive derivation and authorization header attachment.

Network MCP and Cloud MCP are packaged and deployed independently. Compose exposes MCP ports
only to the internal service network with `expose`, not host `ports`, so direct external
ingress is not created by default.

## Consequences

Shared packages can evolve behind typed contracts while services remain container-isolated.
The supervisor no longer fabricates fallback subagent proposals or in-router execution results.
The target agent runtime owns intent planning and policy; MCP packages own only scoped tools and
declarative authorization metadata.
