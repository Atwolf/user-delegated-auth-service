# ADR 0001: Agent Service Multi-Container Boundaries

## Status

Superseded by vNext

This ADR records the earlier multi-container decision, including the local Chainlit
compatibility surface. The vNext runtime topology removes that compatibility service and
standardizes browser and assistant traffic on the AG-UI gateway.

## Context

The supervisor must preserve the Auth0/session boundary, but the target runtime needs separate
protocol, agent, egress, and MCP service boundaries. Each subagent has one unique MCP
configuration and MCP processes must not be shared across subagents.

## Decision

At the time this ADR was accepted, the implementation used a Python monorepo with Pydantic v2
contracts as the stable boundary between services. The supervisor remained as the Auth0
metadata and legacy workflow compatibility surface. The superseded target path was split into
`ag_ui_gateway`, `chainlit_middleware`, `agent_service`, and `egress_gateway` containers. The
Agent Service owned deterministic Coordinator/Dispatcher intent planning and process-local POC
state. The Egress Gateway owned outbound request primitive derivation and authorization header
attachment.

Network MCP and Cloud MCP are packaged and deployed independently. Compose exposes MCP ports
only to the internal service network with `expose`, not host `ports`, so direct external
ingress is not created by default.

## Consequences

Shared packages can evolve behind typed contracts while services remain container-isolated.
The supervisor no longer fabricates fallback subagent proposals or in-router execution results.
The target agent runtime owns intent planning and policy; MCP packages own only scoped tools and
declarative authorization metadata.

## Superseding vNext Decision

The current vNext topology removes `chainlit_middleware` and routes browser assistant traffic
through Next.js `/api/ag-ui` into `ag_ui_gateway` `/agent`. Agent Service now owns thread
creation/restoration, workflow restoration, HITL approval validation, token context lookup,
OBO exchange, egress delegation, and Redis-backed persistence. The frontend
surface is a Next.js assistant-ui AG-UI runtime inside a MUI drawer, with Auth0 session material
kept behind Next.js API routes.
