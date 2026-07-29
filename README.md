# Multi-Agent Hybrid RAG Knowledge Assistant

This repository is being built from the phased implementation blueprint in
[`../plan.md`](../plan.md).

## Live preview

The current frontend preview is available at
[DocPilot on Vercel](https://docpilot-rag-assistant.vercel.app). It includes the
guest Supabase session, connected FastAPI service, document workflows, memory,
human review queue, streamed chat, source evidence, and agent run traces.

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

Phase 7 implements bounded multi-agent orchestration:

- Deterministic routing keeps ordinary questions on the low-latency simple RAG path.
- Typed LangGraph supervisor, planner, retrieval, synthesis, writer, and reviewer nodes.
- Concurrent retrieval through a deny-by-default, read-only tool registry.
- Durable agent steps, sanitized tool calls, and resumable workflow checkpoints.
- Strict step, recursion, concurrency, time, context, and output budgets.
- Prompt-injection containment and citation review before answer publication.

Phase 8 implements attributable, bounded memory:

- Existing conversation messages feed a fixed-size recent-history window.
- Older turns roll into a 4,000-character conversation summary.
- Only explicit `remember...` requests are auto-stored, at confidence `1.0`.
- Private and workspace-shared visibility is enforced with owner-aware RLS.
- Every memory exposes source, confidence, visibility, expiry, and provenance.
- Memory is isolated as untrusted context and cannot replace system instructions
  or document citations.
- Users can inspect and delete memory from the workspace Memory view.
- Expired and soft-deleted records are purged by a daily PostgreSQL cron job.

Phase 9 implements durable human-in-the-loop controls:

- Agentic output pauses before publication when confidence, citation coverage,
  or sensitive-intent policy triggers fire.
- Approval requests are assigned, expire after a bounded window, and escalate
  while pending.
- Authorized reviewers can approve, edit, reject, or request a revision from
  the responsive Review queue.
- Approval and rejection complete in one database transaction; revision rewinds
  the durable LangGraph checkpoint with reviewer feedback.
- Decision keys and database constraints prevent duplicate execution.
- Every decision retains reviewer identity, comment, previous state, final
  state, and timestamp in an immutable audit record.

Phase 10 implements the production product experience:

- Streamed workspace chat with grounded inline citations and protected sources.
- Responsive document, agent-run, review, evaluation, memory, and settings views.
- Virtualized document and trace lists for predictable long-session performance.
- Realtime ingestion and approval refreshes plus explicit offline, cold-start,
  timeout, provider, empty, loading, and retry states.
- Concise execution timelines that expose decisions and tool outcomes without
  internal chain-of-thought.
- Workspace usage counters and guest-first operation across desktop and mobile.

Phase 11 implements bounded production observability and replay:

- Request, run, agent-step, and tool-call correlation with durable trace IDs.
- Redacted structured logs that remove credentials, JWTs, signed query values,
  and sensitive document content.
- End-to-end latency segments plus estimated token accounting for the free Gemini
  integration.
- A per-run diagnostic explorer for retrieval evidence, execution timing, tool
  outcomes, and errors.
- Exact-snapshot and current-configuration replay without inheriting approvals or
  sensitive-action authorization.
- A workspace operations dashboard for success rate, P95 latency, token volume,
  active runs, and trace quota.
- Daily Supabase retention enforcement with a 30-day and newest-50-trace bound.

Phase 12 implements measurable evaluation and release regression:

- A versioned 50-case reviewed suite spanning lookup, synthesis, conflicting
  evidence, missing evidence, and adversarial prompt injection.
- Keyword-only, dense-only, hybrid, simple-RAG, and agentic comparisons.
- Retrieval, citation, groundedness, answer-coverage, safety, latency, token,
  model-call, and failure metrics.
- Durable Supabase results plus a workspace release-gate dashboard.
- A deterministic, provider-free CI regression that blocks citation, safety,
  tenant-isolation, and hybrid-ranking regressions.

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
- [`docs/phase-7-acceptance.md`](docs/phase-7-acceptance.md)
- [`docs/phase-12-acceptance.md`](docs/phase-12-acceptance.md)
- [`docs/development.md`](docs/development.md)
- [`contracts/openapi.yaml`](contracts/openapi.yaml)
- [`contracts/events.asyncapi.yaml`](contracts/events.asyncapi.yaml)
- [`docs/adr/`](docs/adr/)

## Decision status

The values in Phase 0 are implementation defaults. Changing a security boundary,
tenant-ownership rule, public API contract, latency objective, or provider
assumption requires an ADR update.
