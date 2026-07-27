# ADR 0006: Use the Browser History API Until React Router Is Patched

Status: Accepted  
Date: 2026-07-28

## Context

During Phase 1, the npm advisory database reported high-severity vulnerabilities
across the available React Router versions. The newer release's issue concerns
RSC/server actions that this static SPA does not use, but retaining a known high
runtime advisory would fail the repository security gate.

The Phase 1 interface has eight static client routes and needs only navigation,
active-link state, deep-link rendering, and browser back/forward support.

## Decision

Use a small browser History API adapter in `App.tsx` for Phase 1. Do not add
another routing dependency. Reassess React Router during the next dependency
review after a release outside the affected advisory ranges is available.

## Consequences

- The runtime dependency audit can remain free of known high vulnerabilities.
- Current routing behavior stays small and testable.
- Nested routes, loaders, and route-level data APIs are intentionally unavailable.
- A future router migration is isolated to the application shell.
