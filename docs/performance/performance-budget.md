# Performance Budget

Status: Approved Phase 0 engineering target  
Version: 0.1.0  
Scope: Free hosted deployment

## 1. Measurement modes

### Warm

The Render process is running, clients and connection pools are initialized, and
the request does not wait for provider cold start. All primary SLO targets refer
to this mode.

### Cold

The Render service has slept or restarted and must initialize. Cold samples are
reported separately and must never be merged into warm percentiles.

### Cached

The normalized query embedding and retrieval result are valid for the current
workspace index version.

## 2. Warm-path service objectives

| Operation | p50 | p95 | Maximum before controlled timeout |
|---|---:|---:|---:|
| `GET /health` | 50 ms | 150 ms | 1 s |
| Authenticated metadata list | 100 ms | 300 ms | 2 s |
| Cached hybrid retrieval | 80 ms | 250 ms | 1 s |
| Uncached database retrieval, excluding embedding | 150 ms | 500 ms | 2 s |
| Signed upload URL creation | 150 ms | 500 ms | 2 s |
| Approval decision and durable state change | 250 ms | 750 ms | 3 s |
| First token for simple RAG | 1.5 s | 3.5 s | 8 s |
| Complete simple grounded answer | 4 s | 10 s | 30 s |
| Complete multi-agent answer | 8 s | 25 s | 60 s |

These are engineering objectives for the target demo load, not provider-backed
availability or latency guarantees.

## 3. Cold-path objective

- Expected first-request delay: 30 to 90 seconds.
- Frontend detects an unavailable or starting API within 2 seconds.
- Frontend displays a startup state and retries with exponential backoff.
- Retry intervals: 1, 2, 4, 8, 10, and 10 seconds, with jitter.
- User may cancel startup retries.
- Cold-start telemetry records `cold_start=true` and initialization duration.

Artificial uptime traffic is not part of the latency design.

## 4. Simple-RAG latency allocation

| Segment | p50 budget | p95 budget |
|---|---:|---:|
| Edge/network to API | 80 ms | 200 ms |
| JWT verification and authorization | 20 ms | 80 ms |
| Quota and idempotency checks | 20 ms | 60 ms |
| Query normalization/cache lookup | 20 ms | 80 ms |
| Query embedding API | 300 ms | 900 ms |
| Hybrid retrieval RPC | 150 ms | 500 ms |
| Context selection and prompt build | 40 ms | 150 ms |
| Generation to first token | 700 ms | 1.5 s |
| Persistence before/after stream | 100 ms | 400 ms |

Independent operations may overlap. The end-to-end target is therefore lower
than the sum of every worst-case segment.

## 5. Agentic latency allocation

- Router decision: at most 500 ms p95.
- Planner: at most one provider call.
- Independent retrieval subtasks: run concurrently, maximum three.
- Maximum agent nodes: eight.
- Maximum provider retries: two per operation.
- Default run wall timeout: 60 seconds.
- Human approval time is excluded from computational latency.
- Resume from approval should emit a status event within 750 ms p95.

## 6. Capacity test profile

The free-tier release is tested against:

- 10 active workspaces.
- 100 documents per workspace.
- 10,000 active chunks per workspace maximum.
- 768 embedding dimensions when supported by the embedding configuration.
- 10 concurrent browsing users.
- 4 concurrent chat streams application-wide.
- 2 concurrent agent runs per user.
- 3 concurrent ingestion jobs per workspace, with one local consumer process.
- 30 dense and 30 sparse retrieval candidates.
- 6 default and 10 maximum chunks supplied to generation.

This is a protective test profile, not a claim that every free provider will
support all maxima simultaneously.

## 7. Resource budgets

### Backend process

- One application process unless Render memory tests prove additional workers safe.
- No local embedding model.
- Streaming parsers instead of loading entire documents where supported.
- Bounded extracted text and prompt size.
- Reused HTTP and database clients.
- Maximum four active SSE generations per process.

### Database

- Target normal operating size: at most 350 MB.
- Warning threshold: 400 MB.
- Admission-control threshold: 450 MB.
- Detailed traces: 50 per workspace or 30 days, whichever is lower.
- Retrieval cache TTL: 15 minutes by default.
- Query-embedding cache TTL: 24 hours, invalidated by embedding-model version.
- Cleanup jobs remove expired caches and aggregate old telemetry.

### Frontend

- Initial compressed JavaScript target: below 250 KB.
- Route chunks: below 150 KB compressed each.
- No document bytes proxied through the frontend application bundle.
- Trace and evaluation routes are lazy-loaded.
- Lists above 100 visible rows are virtualized or paginated.

## 8. Timeout and retry matrix

| Dependency/operation | Connect | Read/total | Retries | Behavior |
|---|---:|---:|---:|---|
| Supabase metadata query | 1 s | 2 s | 1 | Typed retryable error |
| Hybrid retrieval RPC | 1 s | 2 s | 1 | Retry once if no transaction mutation |
| Gemini embedding | 2 s | 8 s | 2 | Backoff with jitter, then fail/queue |
| Gemini first token | 2 s | 8 s | 1 | Fail before streaming or finish current stream |
| Gemini total generation | 2 s | 30 s | 0 after tokens | Preserve partial failure state |
| Storage signed URL | 1 s | 3 s | 1 | Retryable error |
| Document parser | N/A | 60 s | 0 | Quarantine or fail job |
| Agent run | N/A | 60 s | bounded per node | Controlled terminal state |

Retries apply only when the operation is idempotent or protected by an
idempotency key.

## 9. Required instrumentation

Every request or run records:

- `request_id`, `trace_id`, `run_id`, `workspace_id`, and route.
- Warm or cold classification.
- Authentication and authorization duration.
- Queue duration.
- Embedding duration.
- Retrieval RPC duration.
- Context construction duration.
- Generation time to first token.
- Total generation duration.
- Citation review duration.
- Persistence duration.
- End-to-end duration.
- Candidate and selected chunk counts.
- Input/output token counts and provider status.
- Cache hit/miss and index version.
- HTTP status and stable error code.

Never record secrets, complete prompts, full document text, or hidden reasoning.

## 10. Performance release gates

- Run at least 100 warm samples for metadata and retrieval endpoints.
- Run at least 30 warm simple-RAG samples.
- Run at least 20 warm agentic samples.
- Report p50, p95, maximum, failures, and cold samples separately.
- Explain every p95 miss above 20% of budget.
- Verify SQL plans with `EXPLAIN (ANALYZE, BUFFERS)`.
- Verify no cross-workspace candidate is retrieved under load.
- Stop admissions cleanly when configured concurrency or quota is exhausted.

## 11. Optimization order

1. Remove unnecessary provider calls.
2. Route simple questions away from the agent graph.
3. Reduce database round trips with one hybrid-search RPC.
4. Reuse clients and connections.
5. Bound candidate, context, and token counts.
6. Stream the first token.
7. Cache query embeddings and retrieval results.
8. Tune indexes from measured query plans.
9. Add infrastructure only after measurements demonstrate the need.
