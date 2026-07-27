# Phase 4 Acceptance

## Delivered

- Fixed, recursive, and heading-aware recursive chunking. Heading-aware
  recursive is the default.
- Exact page number, page range, section heading, page-local character offsets,
  strategy, index version, and estimated token count per chunk.
- Zero overlap by default, with bounded configuration for later evaluation.
- Gemini `gemini-embedding-001` document embeddings in bounded batches.
- Manual L2 normalization for 768-dimensional embeddings.
- Rate-limit and transient-provider retry with exponential backoff and jitter.
- Transactional, idempotent chunk upserts using `halfvec(768)`.
- PostgreSQL full-text GIN and HNSW cosine indexes.
- Active index profiles and per-document target/current version tracking.
- Owner-only API and CLI controls for document and workspace re-indexing.
- Re-indexing from retained source pages without downloading the original
  object again.

## Acceptance Evidence

- Connected migration `phase_4_index_construction` applied successfully.
- Rollback-only connected-database acceptance persisted a real
  768-dimensional vector, replaced version 1 with version 2 atomically, retained
  exactly one version-2 chunk, and committed document strategy/version metadata.
- Repeat completion returned successfully without duplicating chunks.
- Connected schema type generation confirms Phase 4 columns and RPC signatures.
- Database size is 12 MB, 2.4% of the 500 MB free-tier planning budget.
- Security advisor has no warning or error. Its single informational
  `index_profiles` notice is intentional: RLS plus revoked client grants makes
  the table service-role-only.
- Performance advisor reports only unused-index informational notices, expected
  while the connected database has no persisted documents or chunks.
- Backend: 63 tests pass at 90.84% aggregate branch coverage.
- Frontend: 29 tests pass at 92.74% statements, 94.8% lines, and 80% branches.
- Ruff, formatting, mypy, OpenAPI/AsyncAPI validation, migration validation,
  frontend lint/typecheck, and the production frontend build pass.

## Runtime Secrets

`GEMINI_API_KEY` and `APP_SUPABASE_SERVICE_ROLE_KEY` are required only in the
backend environment. Neither key may use a `VITE_` prefix or be sent to the
browser. Without both, the ingestion worker remains disabled and queued jobs
stay durable until a correctly configured worker is available.

## Operational Defaults

| Setting | Default |
|---|---:|
| Strategy | `heading_recursive` |
| Target chunk size | 1,800 characters |
| Overlap | 0 characters |
| Embedding model | `gemini-embedding-001` |
| Embedding dimensions | 768 |
| Embedding batch size | 16 |
| Provider retries | 2 |
| Active index version | 1 |
