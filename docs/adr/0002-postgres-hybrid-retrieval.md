# ADR 0002: Use PostgreSQL for Vector, Keyword, Queue, and Initial Cache Workloads

Status: Accepted  
Date: 2026-07-27

## Context

The original project concepts use separate vector, keyword, relational, queue,
and cache services. Separate free services increase latency, operational burden,
and failure modes.

## Decision

Use Supabase PostgreSQL with pgvector, full-text search, and PGMQ. Implement
hybrid retrieval in one workspace-scoped SQL RPC using Reciprocal Rank Fusion.
Use bounded PostgreSQL cache tables for query embeddings and retrieval results.

## Consequences

- Retrieval needs one database round trip.
- Tenant filtering can occur before ranking.
- The 500 MB database allocation is a hard shared constraint.
- Redis or a dedicated vector service may be added behind interfaces only after
  profiling shows that PostgreSQL is the bottleneck.
