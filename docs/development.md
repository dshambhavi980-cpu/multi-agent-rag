# Development Guide

## Prerequisites

- Python 3.12.
- Node.js 24 and npm 11.
- Git.
- Docker Desktop is optional for the local PostgreSQL service.

## First installation

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\apps\api[dev]"
npm install
```

Do not put production credentials in `.env.example`. `.env` and
`apps/web/.env.local` are ignored.

## Run locally

API:

```powershell
Set-Location apps\api
python -m uvicorn app.main:app --reload --port 8000
```

Web application:

```powershell
npm run dev:web
```

Optional database:

```powershell
docker compose up -d postgres
docker compose ps
```

## Quality checks

Backend:

```powershell
Set-Location apps\api
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
python -m pytest
```

Frontend:

```powershell
npm run check:web
```

Contracts and migrations:

```powershell
python scripts\check_contracts.py
python scripts\check_migrations.py
```

End-to-end:

```powershell
npx playwright install chromium
npm run test:e2e
```

## Environment conventions

- Browser-visible variables begin with `VITE_` and are never secrets.
- API variables use `APP_` when they map to typed application settings.
- Provider credentials have provider-specific names and remain server-side.
- Hosted secrets belong in provider secret stores.
- Tests construct settings explicitly and do not depend on the developer's `.env`.

Supabase and ingestion variables:

- `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` are browser-visible.
- `APP_SUPABASE_URL` and `APP_SUPABASE_PUBLISHABLE_KEY` configure FastAPI.
- `APP_SUPABASE_SERVICE_ROLE_KEY` is required for upload finalization and the
  ingestion worker. It must never be exposed through a `VITE_` variable.
- `APP_INGESTION_WORKER_ENABLED` disables the in-process consumer for tests or
  a separately deployed worker.
- Poll, visibility, batch, and parse-timeout variables tune bounded worker
  behavior. The defaults are appropriate for the free-tier target corpus.
- `GEMINI_API_KEY` is a server-only credential required for index construction.
  Do not prefix it with `VITE_`.
- `APP_INDEX_VERSION` selects the target profile version. Increment it only with
  a matching `index_profiles` migration and controlled re-index.
- `APP_INDEX_STRATEGY`, target, overlap, embedding batch, timeout, and retry
  variables are bounded by typed settings. Overlap defaults to zero until an
  evaluation demonstrates a retrieval improvement.
- Query embeddings cache for 24 hours by default. Retrieval results cache for
  15 minutes and are invalidated when workspace document status, index version,
  content type, or tags change.
- RRF defaults to equal dense/sparse weights with `k=60`. Near-duplicate
  suppression defaults to a 0.92 trigram similarity threshold.
- FastAPI verifies user JWTs using the public Supabase JWKS endpoint. It does
  not require the legacy JWT secret.

## Re-indexing

Queue one document:

```powershell
docpilot-reindex `
  --document-id <document-uuid> `
  --workspace-id <workspace-uuid> `
  --actor-id <owner-user-uuid>
```

Queue every ready document in a workspace:

```powershell
docpilot-reindex `
  --workspace `
  --workspace-id <workspace-uuid> `
  --actor-id <owner-user-uuid> `
  --strategy heading_recursive
```

The command requires `APP_SUPABASE_URL` and
`APP_SUPABASE_SERVICE_ROLE_KEY`. The actor must be a workspace owner. Active
jobs are rejected, source pages are retained, and old chunk versions are
removed only after the replacement version commits.

## Retrieval

Use `POST /v1/retrieval/search` with a Supabase bearer token and
`X-Workspace-ID`. The request supports `hybrid`, `dense`, and `sparse` modes:

```json
{
  "query": "ZX-42 reset",
  "mode": "hybrid",
  "limit": 6,
  "candidate_count": 30,
  "filters": {
    "tags": ["operations"],
    "content_types": ["text/markdown"]
  }
}
```

Upload the three files in `benchmarks/retrieval/corpus` to one workspace, then
run the six-case quality comparison:

```powershell
python scripts\benchmark_retrieval.py `
  --token <supabase-access-token> `
  --workspace-id <workspace-uuid>
```

The command exits nonzero unless hybrid mean reciprocal rank exceeds dense-only
mean reciprocal rank.

## Grounded RAG

Create a conversation with a Supabase bearer token, workspace header, and a
unique idempotency key:

```powershell
$headers = @{
  Authorization = "Bearer <supabase-access-token>"
  "X-Workspace-ID" = "<workspace-uuid>"
  "Idempotency-Key" = "conversation-0001"
}
$conversation = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/v1/conversations `
  -Headers $headers `
  -ContentType application/json `
  -Body '{"title":"Operations"}'
```

Start the simple grounded path:

```powershell
$headers["Idempotency-Key"] = "message-request-0001"
$run = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/v1/conversations/$($conversation.id)/messages" `
  -Headers $headers `
  -ContentType application/json `
  -Body '{"content":"How is emergency access rotated?","force_mode":"simple"}'
```

Stream `GET $run.events_url` with the same bearer and workspace headers. Events
are durably sequenced and include retrieval status, validated answer deltas,
available citations, terminal status, and failures. Reconnect with
`Last-Event-ID` to replay only later events. Use `POST /v1/runs/{run_id}/cancel`
with an idempotency key to persist cancellation.

Citation identifiers are stable only within one run. Each `source_url` requires
the same authorization headers and responds with a short-lived Storage redirect;
PDF redirects include `#page=N`. The server drops uncited factual sentences and
unknown citation identifiers before they can become answer events or messages.
When retrieval is empty or too weak, the run completes with
`insufficient_evidence` without calling the generation provider.

`APP_RAG_*` settings bound evidence, candidates, timeout, polling, and heartbeat
behavior. `GEMINI_CHAT_MODEL` defaults to `gemini-3.1-flash-lite`. Prompt files
are immutable versioned assets under `apps/api/app/prompts`; changing behavior
requires a new prompt version and corresponding `PROMPT_VERSION`.

## Endpoint semantics

- `/health` proves process liveness and does not call external dependencies.
- `/ready` evaluates required dependency checks and may return `503`.
- `/version` exposes release, commit, and environment metadata.
- Every API response includes `X-Request-ID`.

## Migrations

Supabase migrations are immutable and ordered by their 14-digit timestamp.
Apply migrations to an empty environment, then run
`supabase/tests/rls_isolation.sql` with `ON_ERROR_STOP=1`. The test creates two
temporary users and workspaces inside a transaction and always rolls back.
Run `supabase/tests/phase3_ingestion.sql` the same way to verify queueing,
idempotent completion, and checksum deduplication.
Run `supabase/tests/phase4_indexing.sql` to verify vector persistence, exact
source-page reuse, controlled version replacement, and repeat completion.
Run `supabase/tests/phase5_retrieval.sql` for workspace isolation, fusion,
filters, cache behavior, deduplication, traces, quality, and determinism.
Run `supabase/tests/phase5_performance.sql` separately; it creates 10,000 chunks
inside a transaction, measures 25 warm uncached searches, enforces p95 below
500 ms, and rolls back.
Run `supabase/tests/phase6_grounded_rag.sql` to verify conversation and run
idempotency, evidence identifier constraints, ordered event persistence, tenant
authorization, and the atomic cancellation/completion race. It always rolls
back.
