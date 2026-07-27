# ADR 0003: Route Simple Questions Outside the Multi-Agent Graph

Status: Accepted  
Date: 2026-07-27

## Context

Running every question through several agents increases provider calls, latency,
cost, failure probability, and quota consumption.

## Decision

Implement a deterministic complexity router. Lookup and ordinary synthesis
questions use a simple hybrid-RAG path. Only questions requiring decomposition,
multiple independent searches, conflict resolution, or approval enter the full
LangGraph workflow.

The router, simple path, and graph share retrieval, citation, policy, and
observability services.

## Consequences

- Common questions have lower latency.
- Agent value can be measured against the simple baseline.
- Routing errors require an evaluation set and visible trace decision.
- The agent graph remains bounded to eight steps by default.
