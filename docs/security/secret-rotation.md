# Secret Rotation

Never commit secrets or copy a service-role key into a `VITE_` variable.

1. Generate the replacement in Gemini or Supabase while the old credential is still valid.
2. Update Render secret variables first: `GEMINI_API_KEY` and, when rotated, `APP_SUPABASE_SERVICE_ROLE_KEY`.
3. Redeploy Render and verify `/health`, `/ready`, retrieval, ingestion, and one grounded answer.
4. Update Vercel only for public values: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY`.
5. Redeploy Vercel and run the guest-mode browser smoke test.
6. Revoke the old credential, inspect audit logs, and record the date and operator outside the repository.

Rotate immediately after accidental disclosure, at maintainer departure, or after unexplained authentication failures. For routine operation, review keys every 90 days. Database backups must be encrypted and stored outside the deployment accounts.
