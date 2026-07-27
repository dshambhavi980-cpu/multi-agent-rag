# Multi-Agent Hybrid RAG Knowledge Assistant

This repository is being built from the phased implementation blueprint in
[`../plan.md`](../plan.md).

## Live preview

The current frontend preview is available at
[DocPilot on Vercel](https://docpilot-rag-assistant.vercel.app). It includes the
Supabase authentication boundary. Deploy the FastAPI service and set
`VITE_API_BASE_URL` to enable the document, retrieval, and chat API workflows
from the public site.

## Current status

Phase 0 established the approved engineering baselines:

- Product requirements and measurable acceptance criteria.
- Threat model and data-ownership boundaries.
- Warm-path performance budget and cold-start expectations.
- Initial OpenAPI and AsyncAPI contracts.
- Free-tier service-limit register and application quotas.
- Architecture decision records.

Phase 1 implements the executable monorepo foundation:

- FastAPI with liveness, readiness, version, request IDs, structured logging,
  typed settings, and tests.
- React/Vite with a responsive operational shell and API status UI.
- Strict Python and TypeScript quality gates.
- Pytest, Vitest, and Playwright test layers.
- Contract and migration validation.
- Docker Compose, CI, Dependabot, pre-commit, and security workflows.

Phase 2 implements the connected Supabase security foundation:

- PostgreSQL tenancy schema with roles, RLS, audit events, pgvector, and PGMQ.
- Private Storage with workspace-scoped object policies.
- Passwordless Supabase Auth and workspace onboarding in React.
- Cached asymmetric JWT verification and RLS-scoped workspace authorization in
  FastAPI.
- Connected-project RLS isolation tests and clean Supabase security advisories.

Phase 3 implements durable document ingestion:

- Browser-side SHA-256 and signed direct-to-Supabase Storage uploads.
- Server-side checksum, size, type, ownership, and deduplication verification.
- PDF, HTML, Markdown, and plain-text parsing with retained page provenance.
- Durable PGMQ jobs with visibility timeouts, bounded retries, quarantine states,
  atomic idempotent completion, and Realtime status updates.
- A responsive document upload and processing workspace.

Phase 4 implements production index construction:

- Fixed, recursive, and heading-aware recursive chunking with exact page and
  character provenance.
- Batched Gemini document embeddings with normalization, bounded retry,
  exponential backoff, and jitter.
- Transactional `halfvec(768)` chunk upserts with PostgreSQL full-text GIN and
  HNSW cosine indexes.
- Versioned index profiles and owner-controlled document or workspace
  re-indexing.
- Index version and strategy visibility in the document workspace.

Phase 5 implements the hybrid retrieval engine:

- One workspace-scoped PostgreSQL RPC for semantic and full-text retrieval.
- Deterministic Reciprocal Rank Fusion with document, date, type, and tag
  filters.
- Bounded trigram near-duplicate suppression.
- Query-embedding and retrieval caches with expiration and index-version
  invalidation.
- Compact ranking traces without raw queries, prompts, or hidden reasoning.
- A six-case benchmark corpus and a rollback-only 10,000-chunk latency gate.

Phase 6 implements grounded, streaming RAG:

- Durable conversations, messages, runs, evidence, and replayable SSE events.
- Versioned Gemini prompts with retrieved document text treated as untrusted data.
- Stable `C1`, `C2`, ... evidence identifiers and sentence-level citation validation.
- Deterministic confidence scoring from retrieval quality, citation coverage, and
  validation results.
- Safe insufficient-evidence, provider-failure, timeout, and cancellation states.
- Workspace-authorized source links that redirect to the exact stored PDF page.

## Quick start

Requirements: Python 3.12+, Node.js 24+, and optionally Docker.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\apps\api[dev]"
npm install
```

Run the API:

```powershell
Set-Location apps\api
python -m uvicorn app.main:app --reload --port 8000
```

Run the web application in a second terminal:

```powershell
npm run dev:web
```

The frontend is available at `http://127.0.0.1:5173` and proxies `/api` to the
backend at `http://127.0.0.1:8000`.

Run all local quality checks:

```powershell
python scripts\check_contracts.py
python scripts\check_migrations.py
Set-Location apps\api
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
python -m pytest
Set-Location ..\..
npm run check:web
```

## Project documents

- [`docs/product-requirements.md`](docs/product-requirements.md)
- [`docs/security/threat-model.md`](docs/security/threat-model.md)
- [`docs/performance/performance-budget.md`](docs/performance/performance-budget.md)
- [`docs/operations/service-limits.md`](docs/operations/service-limits.md)
- [`docs/phase-0-acceptance.md`](docs/phase-0-acceptance.md)
- [`docs/phase-1-acceptance.md`](docs/phase-1-acceptance.md)
- [`docs/phase-2-acceptance.md`](docs/phase-2-acceptance.md)
- [`docs/phase-3-acceptance.md`](docs/phase-3-acceptance.md)
- [`docs/phase-4-acceptance.md`](docs/phase-4-acceptance.md)
- [`docs/phase-5-acceptance.md`](docs/phase-5-acceptance.md)
- [`docs/phase-6-acceptance.md`](docs/phase-6-acceptance.md)
- [`docs/development.md`](docs/development.md)
- [`contracts/openapi.yaml`](contracts/openapi.yaml)
- [`contracts/events.asyncapi.yaml`](contracts/events.asyncapi.yaml)
- [`docs/adr/`](docs/adr/)

## Decision status

The values in Phase 0 are implementation defaults. Changing a security boundary,
tenant-ownership rule, public API contract, latency objective, or provider
assumption requires an ADR update.
