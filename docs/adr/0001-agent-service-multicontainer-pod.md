# ADR 0001: Agent Service Multi-Container Boundaries

## Status

Accepted

## Context

The supervisor must discover subagents from durable SQLite storage and coordinate a
plan-authorize-execute protocol. Each subagent has one unique MCP configuration and MCP
processes must not be shared across subagents.

## Decision

The first implementation uses a Python monorepo with Pydantic v2 contracts as the stable
boundary between services. The supervisor runs as its own HTTP service, discovers enabled
subagents from a mounted SQLite database, and calls subagents through A2A envelopes. Redis
stores temporal state and buffered workflow events. Temporal is included for durable workflow
execution scaffolding.

Each MCP server is packaged and deployed independently. Compose exposes MCP ports only to the
internal service network with `expose`, not host `ports`, so direct external ingress is not
created by default.

## Consequences

Shared packages can evolve behind typed contracts while services remain container-isolated.
The supervisor owns orchestration and discovery, while MCP packages own only their scoped tools
and declarative authorization metadata.
