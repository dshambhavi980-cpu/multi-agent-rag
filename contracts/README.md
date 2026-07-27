# Contracts

## HTTP API

`openapi.yaml` is the initial OpenAPI 3.1 contract for system, document,
conversation, run-stream, and approval operations.

Contract rules:

- `/v1` routes require a Supabase bearer JWT.
- `X-Workspace-ID` selects one active workspace and is always authorized.
- Mutation endpoints that can duplicate work require `Idempotency-Key`.
- Errors use `application/problem+json` and stable uppercase error codes.
- Resource-not-visible may return `404` to avoid disclosing its existence.

## Events

`events.asyncapi.yaml` is the initial AsyncAPI 2.6 contract.

- FastAPI SSE carries ordered, live run events.
- `Last-Event-ID` supports reconnect.
- PostgreSQL remains the durable source of truth.
- Supabase Realtime carries ingestion and approval record changes.
- Events contain concise operational decisions, never hidden chain-of-thought.

Both contracts are version `0.1.0`. Breaking changes require a version update and
an ADR.
