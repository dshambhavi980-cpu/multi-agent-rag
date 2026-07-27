# Phase 2 Acceptance Record

Date: 2026-07-28  
Supabase project: `cggyhjzsjgcsjroxfxlv` (`ap-northeast-1`)  
Database: PostgreSQL 17

## Delivered

- Enabled `vector` 0.8.2 and `pgmq` 1.5.1.
- Added profiles, workspaces, workspace memberships, roles, and immutable
  application audit events.
- Added owner bootstrap, last-owner protection, updated-at triggers, and
  indexed tenant authorization helpers.
- Enabled RLS on every application table and granted only operation-specific
  privileges to `authenticated`.
- Added a private `workspace-documents` bucket with a 25 MB object limit,
  approved MIME types, and workspace-path policies.
- Added rollback-only positive and negative RLS tests for rows, audit metadata,
  updates, final-owner protection, and Storage objects.
- Added cached ES256 JWT verification in FastAPI and an RLS-scoped workspace
  access adapter.
- Added React passwordless authentication, session restoration, workspace
  onboarding, selection, and sign-out.
- Generated browser database types from the connected schema.

## Security Boundary

Storage keys use this format:

```text
<workspace_id>/<uploading_user_id>/<object_name>
```

The database derives the workspace boundary from the first path segment. An
authenticated member may read objects in their workspace and upload only below
their own user segment. An uploader or workspace owner may update or delete an
object.

Workspace authorization is always resolved from `workspace_members`. User
metadata is used only for profile display fields and never for authorization.
The browser receives only a publishable key. A service-role key is optional,
server-side only, and is not needed by the Phase 2 runtime.

## Verification

- Connected-project rollback RLS test: passed.
- Supabase Security Advisor: no findings.
- Supabase Performance Advisor: only expected unused-index informational
  notices on the newly empty schema.
- Backend JWT, authorization, lint, type, and unit gates: passed.
- Frontend auth/workspace lint, type, unit, coverage, and build gates: passed.
- Migration and OpenAPI contract checks: passed.

## Operational Note

The JWT verifier reads the project's public JWKS endpoint and caches keys for
ten minutes, matching Supabase edge caching guidance. It verifies signature,
issuer, audience, expiry, subject, and authenticated role. No JWT shared secret
is stored by this application.
