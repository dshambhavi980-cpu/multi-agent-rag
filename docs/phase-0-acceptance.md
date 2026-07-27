# Phase 0 Acceptance

Status: Complete  
Date: 2026-07-27

## Deliverables

- [x] Product requirements document.
- [x] Target users and release scope.
- [x] Supported document types and 25 MB maximum upload size.
- [x] Owner, reviewer, and member roles.
- [x] Sensitive actions and approval thresholds.
- [x] Threat model for uploads, prompt injection, tenant leakage, unsafe tools,
      secrets, replay, and denial of service.
- [x] Warm and cold latency definitions.
- [x] Warm-path performance budget.
- [x] Free-tier service-limit register.
- [x] Application quotas and capacity thresholds.
- [x] Initial OpenAPI contract.
- [x] Initial AsyncAPI event contract.
- [x] Architecture decision records.

## Exit criteria

### Major features map to measurable acceptance criteria

Satisfied by requirement IDs `FR-001` through `FR-044` and `NFR-001` through
`NFR-009` in `product-requirements.md`.

### Security boundaries and data ownership are unambiguous

Satisfied by:

- Workspace ownership rules in `product-requirements.md`.
- Trust boundaries, data-flow rules, threat register, and release gates in
  `security/threat-model.md`.
- Authenticated workspace-scoped API and event contracts.

### Warm-path SLOs are engineering targets, not guarantees

Satisfied by `performance/performance-budget.md`, which separates warm, cold,
and cached measurements and documents free-hosting limitations.

## Approved implementation defaults

- Public/synthetic data only for the free hosted demo.
- PostgreSQL is the first data plane for vector, keyword, queue, and cache needs.
- Simple RAG is the default path; the agent graph is selected only when needed.
- SSE streams run output; Realtime publishes durable ingestion and approval state.
- Human approval is a durable authorization boundary.

Phase 1 may change these defaults only through a superseding ADR.
