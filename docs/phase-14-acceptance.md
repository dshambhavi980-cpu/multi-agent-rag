# Phase 14 Acceptance

## Deployment artifacts

- Vercel and Cloudflare Pages consume the same tested Vite build.
- Both static hosts have SPA fallback, CSP, clickjacking, MIME-sniffing, referrer, and permissions controls.
- Pull requests receive Cloudflare preview deployments when the repository integration is enabled.
- Render uses one bounded Uvicorn worker, `/health`, dashboard-managed secrets, and conservative ingestion/provider concurrency.
- `supabase/config.toml`, ordered migrations, and `seed.sql` recreate local auth, storage, database, and a non-sensitive demo workspace.

## Release evidence

- `scripts/check_release_config.py` rejects deployment drift or committed secrets.
- `.github/workflows/release.yml` enforces gates, migrations, backend deployment, full smoke, and release recording.
- `scripts/release_smoke.py` verifies health, guest auth, upload, ingestion, hybrid retrieval, and grounded chat against public services.
- `/version` records release identity and a non-secret configuration fingerprint.
- `scripts/rollback_drill.py` validates a known-good target and enforces forward-only database repair.

## Exit criteria

- A clean environment is reconstructable from repository configuration.
- Production provider secrets remain in Render, Supabase, Cloudflare, Vercel, or GitHub environment stores.
- CI and release smoke pass before a release is recorded.
- Rollback is documented and its read-only drill passes against a prior commit.
