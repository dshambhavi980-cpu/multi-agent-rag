# Database migrations

Phase 2 migrations define the Supabase extensions, identity boundary, tenant
roles, RLS policies, audit events, and Storage policies.

Migration filenames must use:

```text
YYYYMMDDHHMMSS_description.sql
```

Applied migrations are immutable. Corrections use a new forward migration.

Run the rollback-only tenant isolation check after applying migrations:

```bash
supabase db reset
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/rls_isolation.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/phase3_ingestion.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/phase4_indexing.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/phase5_retrieval.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/phase5_performance.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/phase6_grounded_rag.sql
```
