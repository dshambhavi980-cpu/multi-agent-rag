# Capacity and Degradation

## Free-tier envelope

- Maximum 5 simultaneous warm API requests per browser session.
- Provider calls are capped at 8 per API process with a 250 ms queue budget.
- User limit: 60 standard or 20 expensive requests per minute.
- Workspace limit: 240 requests per minute.
- Recommended demo corpus: 5,000 chunks or about 100 medium documents per workspace.
- Retrieval uses 30 candidates and returns at most 6 evidence chunks.

Use `phase_13_capacity_snapshot(workspace_id)` to measure chunk count, estimated bytes per 1,000 chunks, and active jobs. Review Supabase database and Render memory metrics before increasing the envelope.

## Degradation order

1. Cached retrieval remains available when Gemini embeddings are quota-limited.
2. Agentic requests fall back to simple RAG only for orchestration unavailability, provider backpressure, or an open provider circuit.
3. Provider calls fail fast with retryable `503` responses instead of building an unbounded queue.
4. PostgreSQL counters return `429` plus `Retry-After` at user or workspace limits.
5. Durable ingestion returns to the queue after restart; exhausted jobs enter quarantine as poison messages.

Retries are limited to idempotent embedding requests and generation requests before any streamed output. Upload finalization, approval decisions, and message creation rely on database idempotency keys and are not blindly replayed by the API.
