# Free-Tier Service-Limit Register

Status: Approved Phase 0 baseline  
Review cadence: Before each release and at least monthly  
Last reviewed: 2026-07-28

Free-tier limits change. Values in this register are planning inputs, not
contractual guarantees. Before deployment, verify them against the linked
provider documentation and the actual account dashboard.

## 1. Provider register

| Service | Planned use | Current planning limit | Operational consequence | Source |
|---|---|---|---|---|
| Cloudflare Pages | React static hosting | 500 builds/month, 20,000 files, 25 MiB per asset on Free | Avoid committing uploaded documents or large generated artifacts to the site | https://developers.cloudflare.com/pages/platform/limits/ |
| Render Free Web Service | FastAPI | Sleeps after 15 minutes idle; 750 free instance hours/workspace/month; ephemeral filesystem | Cold starts are expected; no local persistence; one small process | https://render.com/docs/free |
| Supabase Free | PostgreSQL, Auth, Storage, Realtime | 2 free projects; 500 MB database/project; 1 GB Storage; 5 GB egress; 50,000 MAU; 2 million Realtime messages | Enforce application quotas and retention; one project for the app | https://supabase.com/docs/guides/platform/billing-on-supabase |
| Supabase pgvector | Vector search | Shares the PostgreSQL database allocation | Embeddings and indexes consume the 500 MB database budget | https://supabase.com/docs/guides/ai/vector-columns |
| Supabase PGMQ | Durable jobs | Shares PostgreSQL storage and compute | Archive or delete completed messages; use bounded polling | https://supabase.com/docs/guides/queues |
| Gemini Developer API Free | Generation and embeddings | Model- and region-specific request/token limits; free-tier data treatment applies | Read active limits at startup/configuration time; return `429` safely | https://ai.google.dev/gemini-api/docs/rate-limits |
| Gemini embedding | `gemini-embedding-001` | Free within the model's free tier; account quotas apply | Batch requests and cache query embeddings | https://ai.google.dev/gemini-api/docs/pricing |
| GitHub Actions Free | CI and evaluations | 2,000 minutes/month for private repositories on GitHub Free; public-repository standard runners are generally free | Keep full evaluations manual or scheduled sparingly | https://docs.github.com/en/billing/reference/product-usage-included |

## 2. Application quotas

| Resource | Default limit | Enforcement point | User-visible behavior |
|---|---:|---|---|
| Upload size | 25 MB/file | Signed-upload request and completion validation | Reject with `FILE_TOO_LARGE` |
| Documents | 100/workspace | Upload request | Reject with `WORKSPACE_DOCUMENT_LIMIT` |
| Active chunks | 10,000/workspace | Ingestion admission | Pause job with `WORKSPACE_CHUNK_LIMIT` |
| Concurrent ingestion jobs | 3/workspace | Queue admission | Keep queued or return `INGESTION_CONCURRENCY_LIMIT` |
| Concurrent agent runs | 2/user | Run creation | Return `RUN_CONCURRENCY_LIMIT` and retry time |
| Application-wide chat streams | 4 | API admission | Return `SERVICE_BUSY` |
| Agent steps | 8/run | LangGraph policy | End with `AGENT_BUDGET_EXCEEDED` |
| Provider retries | 2/operation | Provider adapter | End with stable provider error |
| Retrieved chunks | 10/run | Retrieval service | Truncate by fused score |
| Detailed traces | 50/workspace or 30 days | Retention job | Aggregate or delete oldest eligible traces |
| Evaluation cases in routine CI | 10 | CI workflow | Full suite runs manually/scheduled |

## 3. Database storage budget

| Category | Target allocation |
|---|---:|
| Documents and extracted metadata | 35 MB |
| Chunk text and metadata | 90 MB |
| Vector embeddings and indexes | 150 MB |
| Conversations and memory | 25 MB |
| Runs, traces, and approvals | 30 MB |
| Evaluation data | 10 MB |
| Queues and caches | 10 MB |
| Headroom | 150 MB |
| Total | 500 MB |

Phase 4 connected baseline: 12 MB used, 0 persisted documents, and 0 persisted
chunks after rollback-only acceptance testing. This is 2.4% of the 500 MB
planning budget. Re-measure after the first representative 100-document corpus
to establish bytes per chunk and HNSW index overhead.

Phase 5 connected baseline after two rollback-only 10,000-chunk performance
runs: 34 MB used, 0 persisted documents, and 0 persisted chunks. This is 6.8%
of the 500 MB planning budget. The allocated pages are reusable by future chunk
inserts; do not repeat the capacity fixture routinely on the production project.

Threshold actions:

- At 350 MB: report weekly growth and increase cleanup frequency.
- At 400 MB: warn workspace owners and prevent non-essential trace expansion.
- At 450 MB: stop new ingestion and full evaluation runs.
- At 475 MB: emergency cleanup of expired caches and eligible trace detail.

No cleanup may remove approval audit records or active workflow checkpoints.

## 4. Quota behavior

- Quota checks are server-side and workspace-aware.
- Rejections use stable machine-readable error codes.
- `429` responses include `Retry-After` when retry is meaningful.
- Durable jobs remain queued when a transient provider quota is exhausted.
- New model work is rejected before consuming database or provider resources when
  concurrency is full.
- The UI shows current usage and the limit without implying paid capacity.
- Limits are configuration values with secure upper bounds.

## 5. Provider failure modes

### Render sleep or restart

- Frontend displays a startup state.
- Health checks retry with bounded exponential backoff.
- Ingestion jobs remain durable in PGMQ.
- No application state depends on local disk.

### Supabase quota or outage

- Reject new mutations safely.
- Do not claim a queue message if its state cannot be persisted.
- Preserve the request identifier for diagnosis.
- Resume only after health checks pass.

### Gemini quota or regional unavailability

- Stop retries after the configured maximum.
- Mark interactive requests retryable where appropriate.
- Leave durable ingestion jobs queued with delayed visibility.
- Never substitute an unapproved model silently.

### Cloudflare or GitHub limit

- Existing production assets remain independent of CI evaluation jobs.
- Builds and evaluations are scheduled to avoid unnecessary usage.

## 6. Review checklist

- Verify provider limits and pricing pages.
- Verify account-specific Gemini rate limits and region eligibility.
- Record current database and Storage consumption.
- Record average bytes per indexed chunk.
- Record monthly build and CI-minute usage.
- Review quota-related errors and rejected jobs.
- Update application defaults only with a capacity test and ADR when material.
