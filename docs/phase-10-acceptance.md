# Phase 10 Acceptance: Frontend Product Experience

Status: Implemented and deployed to the connected Supabase project.

## Product surfaces

- Guest workspace selection and settings.
- Streamed chat with source filtering, run modes, inline citations, and protected
  source viewing.
- Document upload, ingestion progress, Realtime refresh, and virtualized history.
- Virtualized agent run timeline with concise step and tool summaries.
- Realtime human review queue, evaluation readiness, memory manager, and usage.

## Resilience and accessibility

- Stable answer containers prevent layout shifts during streaming.
- Offline, cold-start, rate-limit, timeout, provider, empty, loading, error, and
  retry states use plain recovery language.
- Upload, chat, navigation, source closing, and approval controls are operable by
  keyboard with visible focus and accessible labels.
- Desktop and mobile layouts use bounded scroll areas and responsive navigation.
- Internal prompts, tool inputs, accumulated drafts, and chain-of-thought are not
  returned by the product trace APIs.

## Data and API

- Added workspace-scoped `list_rag_runs`, `get_agent_run_trace`, and
  `get_workspace_usage` RPCs restricted to the service role.
- Added authenticated FastAPI endpoints for recent runs, concise traces, and
  workspace usage.
- SSE closes cleanly when a run pauses for human approval.
- OpenAPI documents all Phase 10 read endpoints and response models.

## Verification

- Python: Ruff, MyPy, 103 Pytest tests, and at least 90% backend coverage.
- Web: ESLint, TypeScript, Vitest with enforced 85% line/function/statement and
  80% branch thresholds, plus production Vite build.
- Contracts and all Supabase migrations pass repository validation.
