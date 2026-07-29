# Phase 9 Acceptance: Human-in-the-Loop Controls

Status: Implemented and deployed to the connected Supabase project.

## Policy boundary

Agentic runs are evaluated after the reviewer node and before an assistant
message is published. The workflow pauses when:

- Grounded-answer confidence is below `APP_APPROVAL_CONFIDENCE_THRESHOLD`.
- Citation coverage is below `APP_APPROVAL_CITATION_COVERAGE_THRESHOLD`.
- The request contains a sensitive or external-action intent.

Safe insufficient-evidence responses remain terminal fallbacks and do not create
review noise.

## Durable state

`approval_requests` stores assignment, risk, reasons, proposed output, answer
metadata, expiration, reviewer identity, and decision. `approval_decisions`
stores the immutable decision key, action, comment, previous state, and final
state.

Both tables use RLS. Workspace owners and members may review; viewers cannot.
Assigned requests are visible to the assignee and workspace owners. Backend RPCs
repeat the role and assignment checks before any decision.

## Decision semantics

| Action | Workflow result |
| --- | --- |
| Approve | Publishes the original or edited output and completes the run atomically |
| Reject | Cancels the run with a non-retryable `HUMAN_REJECTED` terminal state |
| Request revision | Rewinds the checkpoint to the writer with reviewer feedback |
| Expire | Fails the run with `APPROVAL_EXPIRED`; no output is published |

One pending request is allowed per run. Creation keys make repeated pause
attempts idempotent. Reviewer decision keys make repeated submissions return the
recorded decision without repeating workflow execution.

## Review queue

The `/approvals` workspace view includes:

- Pending, all, approved, and rejected filters.
- Risk, trigger reason, run ID, and request time.
- Editable proposed output and required reviewer comment.
- Approve, request-revision, and reject actions.
- Loading, empty, error, pending, and decided states.
- Responsive desktop and mobile layouts.

## Verification

- Backend: 102 tests passed; 90.07% branch-aware coverage.
- Frontend: 34 tests passed; configured coverage thresholds passed.
- Ruff, mypy strict mode, ESLint, TypeScript, contract checks, migration checks,
  and the Vite production build passed.
- Supabase: two approval tables, four public RPCs, RLS on both tables, and five
  Phase 9 foreign-key indexes verified.
- Supabase advisors: no remaining Phase 9 unindexed-foreign-key findings.
  Anonymous-session notices are expected because DocPilot intentionally offers
  guest access; workspace membership and reviewer-role checks still apply.

## Exit criteria

| Criterion | Evidence |
| --- | --- |
| A paused workflow cannot continue without an authorized decision | `awaiting_approval` run state plus role-checked decision RPC |
| Every decision is auditable | Immutable `approval_decisions` previous/final state record |
| Duplicate submissions cannot execute twice | Unique creation and decision keys with row locks |
| Rejection produces a safe terminal state | Transactional `cancelled` run with no output message |
