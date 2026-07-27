# ADR 0005: Make Human Approval a Durable Authorization Boundary

Status: Accepted  
Date: 2026-07-27

## Context

Low-confidence output, shared memory changes, external publication, and future
side effects must not continue based on model judgment alone.

## Decision

Human approval is a durable LangGraph node backed by an `approval_requests`
record and workflow checkpoint. Only workspace owners and reviewers may decide.
State transitions are transactional, idempotent, and audited.

Replay creates a new run and never inherits authorization for a sensitive action.

## Consequences

- A process restart cannot bypass approval.
- Approval latency is excluded from compute SLOs.
- UI and API authorization require race-condition tests.
- Future tools can reuse the same approval boundary.
