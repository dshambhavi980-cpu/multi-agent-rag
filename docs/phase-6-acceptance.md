# Phase 6 Acceptance: Grounded RAG and Citations

## Delivered behavior

Phase 6 adds a simple RAG path before agent orchestration. A user message creates
one durable run, hybrid retrieval selects workspace-scoped chunks, and selected
evidence is persisted as `C1`, `C2`, and later identifiers in deterministic rank
order before generation begins.

The Gemini system and answer prompts are versioned files. They state that
retrieved text is untrusted evidence, not an instruction source. Generation is
streamed from Gemini, buffered to sentence boundaries, and validated before any
answer delta is published. A factual sentence is accepted only when all of its
citation identifiers belong to that run's evidence allow-list. Unknown
identifiers and uncited claims are discarded.

Confidence is deterministic:

```text
45% retrieval quality + 35% accepted-claim coverage + 20% validation score
```

Conflicting evidence caps confidence at `0.35`. Empty or weak retrieval returns a
fixed `insufficient_evidence` response without a model call.

## Durable lifecycle

The database stores conversations, messages, runs, selected evidence, and ordered
events. Run creation is idempotent. Partial validated output is persisted while
generation is active. Provider failure, timeout, client cancellation, and user
cancellation become explicit terminal states.

Completing a run that has entered `cancelling` atomically changes it to
`cancelled`; it cannot publish an assistant message. SSE reconnects use
`Last-Event-ID` and the persisted event sequence, so a process-local buffer is not
required for replay.

## Source accuracy

Each citation contains the document ID, chunk ID, label, page, section, exact
quote, and a stable API source URL. The source endpoint rechecks workspace access,
creates a short-lived signed URL for the original private Storage object, and
adds `#page=N` for PDF sources.

## Verification

- Backend: 85 tests pass with 92.43% line coverage.
- Frontend: lint, TypeScript, 29 tests, coverage, and production build pass.
- Static analysis: Ruff and the intended mypy `app tests` scope pass.
- Contracts: 29 OpenAPI paths and 3 AsyncAPI channels validate.
- Migrations: all 13 ordered migrations validate.
- Live isolated smoke: ingestion reached `ready`; a grounded run completed with
  `C1`; its source endpoint returned a signed `307`; and an unsupported filtered
  question completed as `insufficient_evidence`.
- Observed warm time to first validated answer delta: `3291 ms`, below the
  `3500 ms` warm target. This is a smoke sample, not a statistically valid p95.
- Connected database: run `supabase/tests/phase6_grounded_rag.sql`; it is a
  rollback-only acceptance transaction.

## Exit criteria mapping

| Criterion | Evidence |
| --- | --- |
| Citation opens correct document/page | Authorized signed-source route plus route and Storage tests |
| No out-of-context citation | Sentence validator and database citation constraints |
| Unsupported question fails safely | Static insufficient-evidence path and unit coverage |
| Warm time to first token | Live smoke observed 3291 ms; Phase 12 must establish p95 on the complete evaluation corpus |

The warm target remains dependent on Supabase and Gemini free-tier availability.
Cold starts are measured separately and are not represented as warm-path
performance.
