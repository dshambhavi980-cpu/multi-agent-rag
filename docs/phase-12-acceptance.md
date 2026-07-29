# Phase 12 Acceptance: Evaluation and Regression

## Delivered system

Phase 12 adds a production evaluation system around the existing hybrid RAG and
agentic workflows:

- A versioned, human-reviewed suite of 50 questions with ten lookup, synthesis,
  conflicting-evidence, missing-evidence, and prompt-injection cases.
- Expected source filenames, source-chunk hints, required facts, forbidden
  answer terms, tenant-isolation sources, and critical-case labels.
- Comparable keyword-only, dense-only, hybrid, simple-RAG, and agentic variants.
- Retrieval recall, reciprocal rank, and nDCG scoring.
- Citation precision and recall, groundedness, answer coverage, safety, and
  tenant-isolation scoring.
- Per-case latency, model-call, prompt-token, output-token, status, and failure
  recording.
- Durable Supabase runs and results, protected by service-role-only RPC access.
- A release dashboard with aggregate quality, safety, latency, and failure
  metrics.
- A deterministic pull-request regression that fails CI when a release gate
  regresses.

The implementation uses the existing free stack. Retrieval-only comparisons use
Supabase and Gemini embeddings; answer variants use the configured Gemini free
quota. No additional API key is required.

## Release gates

A complete release evaluation passes only when all of these conditions hold:

| Gate | Threshold |
| --- | ---: |
| Citation precision | at least 0.95 |
| Critical prompt-injection safety | 1.00 |
| Tenant-isolation safety | 1.00 |
| Hybrid nDCG improvement over dense | at least 10% |

An omitted metric fails closed. A failed gate is stored with the run and shown
in the dashboard, making a configuration regression visible and release
blocking.

## Metric definitions

- Retrieval recall: fraction of expected sources found in the returned set.
- Reciprocal rank: inverse rank of the first relevant result.
- nDCG: discounted ranking quality normalized by the ideal relevant ordering.
- Citation precision: fraction of returned citations matching expected sources.
- Citation recall: fraction of expected sources represented by citations.
- Groundedness: supported citation coverage for answers expected to be grounded.
- Answer coverage: fraction of reviewed expected facts present in the answer.
- Safety: no forbidden term or forbidden source appears, with the correct
  insufficient-evidence behavior where required.
- Hybrid gain: `(hybrid nDCG - dense nDCG) / dense nDCG`.

All aggregate values are computed from durable per-case records. P95 latency,
model calls, token counts, and failure rate are retained alongside quality.

## Deterministic PR regression

The small regression suite uses reviewed, fixed retrieval rankings and answer
outputs. It requires no network or provider key and runs in every pull request:

```powershell
python scripts\check_evaluation_regression.py
```

The Phase 12 baseline is:

| Metric | Baseline |
| --- | ---: |
| Hybrid nDCG | 1.0000 |
| Dense-only nDCG | 0.7768 |
| Keyword-only nDCG | 0.9631 |
| Hybrid gain over dense | 28.74% |
| Citation precision | 1.0000 |
| Citation recall | 1.0000 |
| Groundedness | 1.0000 |
| Answer coverage | 0.7708 |
| Critical safety | 1.0000 |
| Tenant isolation | 1.0000 |

This demonstrates a measurable hybrid advantage above the 10% release
threshold. Any future snapshot or scoring change that falls below a gate exits
non-zero and blocks CI.

## Running a live evaluation

1. Open **Evaluations** in the DocPilot workspace.
2. Select keyword, dense, and hybrid for an inexpensive retrieval comparison.
3. Add simple RAG and agentic when answer-quality comparison is needed.
4. Choose between 1 and 50 reviewed cases and start the run.
5. Keep the page open or return later; the run and every case result are stored
   in Supabase.
6. Inspect the release gate, aggregate metrics, and failed case rows.

Run the 50-case retrieval suite after changes to chunking, embedding, ranking,
or document filtering. Run all five variants before releases that modify
prompts, generation, tools, citations, memory, or agent routing. Because answer
variants consume Gemini quota, schedule the full provider-backed suite manually
or sparingly; the deterministic suite remains mandatory on every pull request.

## Retention and operations

- At most one evaluation may be active for a user at a time.
- Execution is sequential to stay within free-provider rate limits.
- Aggregate run records remain available while detailed results are bounded to
  the newest 20 runs by the daily Supabase retention job.
- Provider and case failures are recorded as sanitized failure codes; secrets
  and document bodies are not stored in result metadata.
- A service restart may interrupt an active background evaluation. Restart
  recovery belongs to the later resilience phase; rerun the evaluation if it
  remains active after a deployment.

## Acceptance evidence

- `apps/api/app/evaluation_suites/phase12_v1.json` contains 50 unique reviewed
  cases and all five required categories.
- `scripts/check_evaluation_regression.py` enforces deterministic release gates.
- `supabase/migrations/20260729220000_phase_12_evaluation_system.sql` provides
  durable, tenant-scoped evaluation storage and retention.
- API, metric, service, route, and dashboard tests run in the standard backend
  and frontend CI jobs.
- The OpenAPI contract exposes suite, create, list, and detail endpoints.
