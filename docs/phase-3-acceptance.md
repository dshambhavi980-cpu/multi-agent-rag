# Phase 3 Acceptance

## Delivered

- Signed, direct-to-Storage uploads scoped to a user and workspace.
- Browser and server SHA-256 verification with a 25 MB application limit.
- Extension, MIME, signature, size, checksum, session, object-owner, and
  workspace validation.
- Workspace-local checksum deduplication.
- Durable PGMQ ingestion with visibility timeout recovery after process exit.
- Bounded retries for transient failures and terminal quarantine for malformed
  or encrypted content.
- PyMuPDF PDF extraction, BeautifulSoup HTML extraction, and strict UTF-8 text
  and Markdown parsing.
- Normalized pages and provenance-first chunks committed atomically.
- Realtime document and job status updates with browser polling fallback.

## Acceptance Evidence

- Connected migration `phase_3_document_ingestion` applied successfully.
- Connected migration `phase_3_fk_indexes` applied successfully.
- Transactional connected-database test passed for queue claim, processing,
  repeat completion, chunk idempotency, and duplicate upload detection.
- Supabase security advisor reports no findings.
- Foreign-key advisor findings were resolved with correctly ordered composite
  indexes. Unused-index informational notices are expected while the database
  is empty.
- Backend: 40 tests pass at 90.37% aggregate coverage.
- Frontend: 29 tests pass at 92.72% statements, 94.77% lines, and 80.32%
  branches.

## Runtime Secret

`APP_SUPABASE_SERVICE_ROLE_KEY` must be present only in the backend environment.
Without it, authenticated browsing remains available but upload finalization
and ingestion return a controlled `503`; no privileged key is sent to the
browser.
