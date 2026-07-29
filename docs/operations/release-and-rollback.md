# Release and Rollback

## Provider configuration

The public frontend remains [DocPilot on Vercel](https://docpilot-rag-assistant.vercel.app). The same static build can be deployed to Cloudflare Pages through `.github/workflows/cloudflare-pages.yml` after setting `CLOUDFLARE_PAGES_ENABLED=true`.

Render secrets:

- `APP_SUPABASE_URL`
- `APP_SUPABASE_PUBLISHABLE_KEY`
- `APP_SUPABASE_SERVICE_ROLE_KEY`
- `GEMINI_API_KEY`

GitHub production environment secrets:

- `SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_ID`, `SUPABASE_DB_PASSWORD`
- `RENDER_DEPLOY_HOOK_URL`
- `VERCEL_DEPLOY_HOOK_URL`
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`
- `APP_SUPABASE_SERVICE_ROLE_KEY` for smoke-test cleanup

GitHub variables:

- `VITE_API_BASE_URL=https://docpilot-api-w6hj.onrender.com`
- `PRODUCTION_FRONTEND_URL=https://docpilot-rag-assistant.vercel.app`
- `CLOUDFLARE_PAGES_ENABLED=false` until Cloudflare credentials are connected

Cloudflare additionally requires `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. No server secret is exposed to a `VITE_` variable.

## Release

1. Merge only after CI, evaluation regression, migration, and release-config checks pass.
2. Run the `Production Release` workflow with an immutable release identifier.
3. The workflow applies reviewed migrations before triggering Render and waits until `/version` reports the release commit.
4. It runs `scripts/release_smoke.py`, covering health, anonymous auth, upload, ingestion, hybrid retrieval, and grounded chat.
5. After the backend smoke passes, it triggers the Vercel production deployment and verifies the public frontend.
6. It stores a release manifest containing commit, configuration fingerprint, URLs, and API/frontend security headers.
7. Deploy Cloudflare Pages only when its repository variable is enabled; Vercel remains the primary public frontend.

## Rollback

Application rollback is a reviewed revert commit. Database migrations are never rolled back destructively in production; incompatible schema changes receive a forward corrective migration.

Run a drill before release:

```powershell
python scripts/rollback_drill.py HEAD~1 --json
```

Then, during an incident:

1. Freeze releases and record the failing release manifest.
2. Revert the application range identified by the drill on a branch.
3. Add a forward database fix if migrations after the target are incompatible.
4. Run CI and the full release smoke suite.
5. Merge, trigger Render, and redeploy the static frontend.
6. Confirm `/version` reports the intended commit and configuration fingerprint.

The drill is intentionally read-only: it validates ancestry, lists schema changes after the target, and prints the exact recovery sequence without touching Git or providers.
