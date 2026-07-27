# Phase 5 Acceptance

## Delivered

- Semantic cosine search over normalized `halfvec(768)` embeddings.
- Indexed PostgreSQL full-text search using `websearch_to_tsquery`.
- One workspace-scoped hybrid-search RPC with an explicit actor membership
  check before any candidate query.
- Deterministic Reciprocal Rank Fusion with stable UUID tie-breaking.
- Hybrid, dense-only, and sparse-only modes for evaluation.
- Document, creation date, content type, and tag filters applied before ranking.
- Near-duplicate suppression over the bounded fused candidate set using
  `pg_trgm`.
- Query-embedding cache with model/dimension keys and a 24-hour default TTL.
- Retrieval-result cache with a 15-minute default TTL and workspace index
  fingerprint.
- Trigger-based invalidation when relevant document metadata or index state
  changes.
- Ranking traces containing identifiers, ranks, scores, cache state, and
  timings, but no raw query or document content.
- Six relevance cases with a three-document corpus and a live API benchmark
  runner.

Optional reranking remains disabled. The measured SQL benchmark clears the
latency target without another model call, and no quality evidence currently
justifies adding that latency.

## Connected Acceptance

- Migrations `phase_5_hybrid_retrieval` and
  `phase_5_halfvec_operator_path` applied successfully.
- The full schema compiled first in a connected rollback-only transaction.
- A stronger candidate in another workspace was excluded from every result.
- Hybrid RRF ranked the exact `ZX-42` procedure first while dense-only ranked
  the semantic distractor first: reciprocal rank `1.0` versus `0.5`.
- Near-duplicate suppression removed the lower-ranked copy.
- Repeated uncached and cached searches returned identical item ordering.
- Document tags filtered candidates before ranking.
- A non-member received PostgreSQL `42501`.
- Query-embedding and retrieval-result caches round-tripped successfully.
- Updating indexed document metadata invalidated workspace retrieval cache.
- Trace rankings contained no query or chunk text.
- A live Gemini `RETRIEVAL_QUERY` request returned one normalized
  768-dimensional embedding.
- The live six-case API benchmark scored hybrid MRR `1.0` and dense-only MRR
  `0.9167`; hybrid ranked every expected document first.
- Repeating the same live hybrid request hit the retrieval-result cache.
- The temporary benchmark workspace and Auth user were removed successfully
  after cascading document, membership, cache, and trace cleanup.
- Direct deletion of a workspace's final owner remains blocked while parent
  workspace deletion now cascades cleanly.

## Performance Evidence

The connected performance fixture generated 10,000 indexed chunks in one
workspace, ran one warm-up and 25 warm uncached hybrid searches, and rolled the
transaction back.

| Metric | Result | Budget |
|---|---:|---:|
| p50 | 34.013 ms | 150 ms |
| p95 | 34.810 ms | 500 ms |
| maximum | 35.937 ms | 2,000 ms |

Both `document_chunks_embedding_hnsw_idx` and
`document_chunks_search_idx` recorded 26 scans during the measured run.

## Quality Gates

- Backend: 71 tests pass at 91.67% aggregate branch coverage.
- Frontend: 29 tests pass at 92.74% statements, 94.8% lines, and 80%
  branches.
- Playwright: 2 Chromium end-to-end tests pass.
- OpenAPI: 28 HTTP paths validate with unique operation identifiers.
- Migration ordering: 11 migrations validate.
- Ruff, formatting, and strict mypy pass.

## Security Review

- Query and retrieval cache tables are service-role-only: RLS is enabled, client
  grants are revoked, and no client policy exists by design.
- Retrieval traces are visible only to workspace owners and reviewers.
- Privileged functions are executable only by `service_role` and verify the
  supplied actor against `workspace_members`.
- The Supabase advisor reports an account-level warning that leaked-password
  protection is disabled. The current application is passwordless-only, but the
  protection should be enabled before any password authentication is offered.
