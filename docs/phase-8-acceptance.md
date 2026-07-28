# Phase 8 Acceptance: Memory System

## Delivered behavior

Phase 8 reuses the durable `messages` table as the conversation source of truth.
Each run retrieves up to eight recent messages, the bounded conversation summary,
and up to eight visible long-term memories. Context construction is capped at
6,000 characters and runs concurrently with document retrieval on the simple RAG
path.

Automatic long-term storage is deliberately narrow. Only a direct user statement
matching `remember...` is stored automatically, with confidence `1.0`, private
visibility, and the source message attached. The schema also supports
human-approved and workspace-shared records for later review workflows.

## Safety and isolation

`memory_items` has RLS enabled. Private records are visible only to their owner;
records from another user are visible only when their visibility is explicitly
`workspace` and the caller is a member of that workspace. Backend RPCs repeat the
workspace and actor checks even though they execute through the service role.

Retrieved history and memory are wrapped in an `untrusted_memory` boundary.
The prompt states that memory is contextual data, not instructions or factual
evidence. The existing citation reviewer therefore continues to require document
evidence for published factual claims.

Deletion is immediate for retrieval: the owner-only delete RPC sets `deleted_at`,
and every list and retrieval query excludes deleted or expired records. A daily
`pg_cron` job permanently purges expired records after seven days and soft-deleted
records after thirty days. The API also performs rate-limited opportunistic
cleanup.

## User controls

The Memory view provides:

- Private, workspace, and combined filters.
- Visible source type, confidence, visibility, and expiration.
- Expandable source excerpts for provenance.
- Owner-only deletion controls.
- Loading, empty, failure, and read-only shared-memory states.

## Verification

- Backend: 99 tests pass at 90.29% total coverage.
- Frontend: 32 tests pass above all configured coverage thresholds.
- Static analysis: Ruff, strict mypy, TypeScript, and ESLint pass.
- Build: the Vite production bundle completes successfully.
- Database: RLS enabled, two memory policies, six RPCs, three summary columns,
  and one scheduled retention job verified in the connected Supabase project.
- Performance: all Phase 8 foreign keys have covering indexes.

## Exit criteria mapping

| Criterion | Evidence |
| --- | --- |
| Memory always has visible provenance | Source type and excerpt are required in the schema, API, and UI |
| Deleted memory is no longer retrievable | Soft-delete RPC plus `deleted_at is null` in all read paths |
| Cross-user memory requires explicit sharing | Owner-or-workspace RLS and RPC filters |
| Long conversations stay within a fixed prompt budget | Eight recent turns, 4,000-character summary, 6,000-character final memory budget |
