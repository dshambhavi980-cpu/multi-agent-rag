# Phase 13 Acceptance

Phase 13 hardens DocPilot for a documented free-tier production envelope. It does not claim that free hosting can provide guaranteed latency during provider cold starts.

## Production target

| Path | Warm p95 target | Free-tier test load |
| --- | ---: | ---: |
| Health/readiness | 250 ms | 10 concurrent |
| Cached retrieval | 800 ms | 5 concurrent |
| Uncached retrieval | 2,500 ms | 3 concurrent |
| First streamed answer token | 3,000 ms | 2 concurrent |
| Approval decision | 1,000 ms | 3 concurrent |

Run `python scripts/load_phase13.py --base-url <url> --requests 50 --concurrency 5`. Add `--token` and `--workspace-id` for retrieval. Streaming/chat and approval scenarios require seeded IDs and are exercised by the end-to-end suite.

## Exit evidence

- Backend: Ruff, mypy, and 90% pytest coverage.
- Frontend: ESLint, TypeScript, Vitest, production build, and Playwright.
- Database: migration checks, RLS isolation suite, security/performance advisors, rate-limit RPC tests, and `scripts/profile_phase13.sql`.
- Supply chain: `pip-audit`, production `npm audit`, and an uploaded CycloneDX SBOM.
- Recovery: stale ingestion is requeued or quarantined; stale generation/evaluation is closed with a retryable error.

Record dated load-test results here before raising the limits. A cold Render instance is measured separately and excluded from warm SLOs.
