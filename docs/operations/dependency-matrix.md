# Dependency Timeout and Retry Matrix

| Dependency | Timeout | Retry | Circuit/backpressure | Failure behavior |
| --- | ---: | ---: | --- | --- |
| Supabase Auth/Data/RPC | 3 s | None at HTTP layer | PostgreSQL request limits | Retryable service error |
| Supabase Storage | 3 s | None | Upload size and integrity limits | Upload remains resumable |
| Gemini embeddings | 30 s | 2, 429/5xx only | 8 concurrent, 250 ms queue, 5 failures/30 s | Retrieval/ingestion reports retryable failure |
| Gemini generation | 30 s | 1, only before first token | 8 concurrent, 250 ms queue, 5 failures/30 s | Agentic may degrade; simple RAG fails safely |
| RAG run | 45 s | None | User/workspace counters | Durable failed/timed-out run |
| Agent workflow | 60 s, 8 steps | Node-local idempotent work only | 3 concurrent retrievals | Safe simple-RAG degradation where valid |
| Ingestion parse | 45 s | Durable queue, max 3 | Batch size 2 | Requeue, then quarantine |

All values are environment-configurable through `.env.example`.
