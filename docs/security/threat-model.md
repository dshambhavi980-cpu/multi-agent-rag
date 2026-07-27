# Threat Model

Status: Approved Phase 0 baseline  
Version: 0.1.0  
Method: Asset and trust-boundary review with STRIDE-style threat classification

## 1. Security objectives

1. Prevent one workspace from accessing or inferring another workspace's data.
2. Treat uploaded and retrieved document text as untrusted input.
3. Prevent model output from granting permissions or invoking unapproved tools.
4. Keep provider credentials, service-role keys, JWTs, and signed URLs secret.
5. Make sensitive actions explicit, authorized, idempotent, and auditable.
6. Keep free-tier resources available under accidental or malicious load.

## 2. Assets

| Asset | Owner | Sensitivity | Required protection |
|---|---|---|---|
| Original documents | Workspace | High | Tenant isolation, encryption in transit, controlled deletion |
| Extracted text and chunks | Workspace | High | RLS, retrieval scoping, retention |
| Embeddings | Workspace | High | Treat as derived sensitive data |
| Conversations | User in workspace | High | User/workspace authorization |
| Shared memories | Workspace | High | Approval, provenance, deletion |
| Private memories | User | High | User-only RLS |
| Agent runs and traces | Workspace/user | Medium to high | Redaction, bounded retention |
| Approval records | Workspace | High integrity | Immutable audit trail |
| Provider credentials | Application operator | Critical | Server-side secrets only |
| Evaluation corpus | Workspace or system | Medium | Provenance and tenant scoping |

## 3. Trust boundaries

1. Browser to Cloudflare-hosted frontend.
2. Browser to FastAPI over TLS.
3. Browser to Supabase Auth, Realtime, and signed Storage endpoints.
4. FastAPI to Supabase using user JWT or service credentials.
5. FastAPI to Gemini APIs.
6. PGMQ job claim to backend job execution.
7. Untrusted document text entering parser, retrieval context, and model prompt.
8. Model output entering application state, citations, memory, and approval.

The browser is untrusted. Document content is untrusted. Model output is
untrusted until schema, authorization, citation, and policy checks succeed.

## 4. Data-flow security rules

- The browser receives only the Supabase anonymous key, never the service-role key.
- FastAPI verifies the JWT issuer, audience, expiry, and signature.
- FastAPI derives user identity from the verified token, never request body fields.
- Every database query includes an authorized `workspace_id`.
- RLS remains enabled even when API checks exist.
- Service-role access is limited to background operations that cannot use user RLS.
- Signed upload and download URLs are short-lived and scoped to one object.
- File bytes upload directly to Storage.
- Retrieved document text is wrapped as evidence, not instructions.
- Agent tools use allowlisted schemas and server-side authorization.
- Model-produced identifiers are validated against server-owned records.

## 5. Threat register

| ID | Threat | Risk | Required controls | Verification |
|---|---|---:|---|---|
| T-001 | User changes `workspace_id` to access another tenant. | Critical | Verified identity, membership check, RLS, workspace-first indexes. | Cross-tenant API and SQL tests. |
| T-002 | Service-role query omits tenant filter. | Critical | Repository boundary, mandatory workspace parameter, review rule, integration tests. | Seed two tenants and inspect all privileged paths. |
| T-003 | Retrieved document contains prompt-injection instructions. | High | Treat context as quoted evidence, fixed tool policy, no instruction elevation, reviewer checks. | Adversarial document evaluation set. |
| T-004 | Model invents a citation identifier. | High | Allowlist citations from supplied context; reject unknown IDs. | Citation validator unit and end-to-end tests. |
| T-005 | Model requests an unauthorized tool or side effect. | Critical | Typed tool registry, per-tool authorization, deny-by-default policy, approval node. | Tool-policy tests and malicious model fixtures. |
| T-006 | Malformed or hostile upload crashes parser. | High | MIME and signature checks, size limit, parser timeout, isolated job failure, dependency scanning. | Corrupt, oversized, polyglot, and encrypted file tests. |
| T-007 | Duplicate request repeats upload, approval, or workflow action. | High | Idempotency keys, unique constraints, transactional state transitions. | Concurrent duplicate-submission tests. |
| T-008 | API key or signed URL leaks through logs or traces. | Critical | Structured redaction, no request-header logging, short URL expiry, secret scan. | Log fixture and repository scans. |
| T-009 | Free-tier quota exhaustion causes denial of service. | High | Application quotas, bounded concurrency, rate counters, backpressure, typed `429`. | Load and quota-boundary tests. |
| T-010 | Large prompt or agent loop causes resource exhaustion. | High | Token budgets, maximum 8 steps, two retries, wall timeout, context truncation. | Budget enforcement tests. |
| T-011 | User escalates role through client request. | Critical | Owner-only role mutation, RLS, server-derived actor, audit. | Member/reviewer negative tests. |
| T-012 | Approval is decided by unauthorized user. | Critical | Owner/reviewer check, row lock, one-way state machine, audit event. | Authorization and race tests. |
| T-013 | Replayed run repeats a sensitive action. | High | Replay creates a new run and approval; side effects never replay automatically. | Replay integration test. |
| T-014 | Deleted document remains searchable through cache or chunks. | High | Transactional tombstone, index-version bump, cache invalidation, asynchronous purge. | Delete-then-search test. |
| T-015 | Long-term memory stores false or sensitive information. | High | Confidence/provenance fields, approval for shared memory, user controls, expiration. | Memory policy and deletion tests. |
| T-016 | SSE stream exposes another user's run. | Critical | Authenticate before stream, authorize run ownership/workspace, non-guessable IDs. | Cross-user stream test. |
| T-017 | CORS or XSS steals an authenticated session. | High | Strict origin allowlist, secure headers, React escaping, no raw HTML, short sessions. | Security-header and XSS tests. |
| T-018 | SQL or full-text query injection. | High | Parameterized SQL/RPC, no string-built filters, validated sort/filter enums. | Injection test corpus. |
| T-019 | Provider receives sensitive portfolio data. | Medium | Demo uses public/synthetic documents; disclose provider processing; future provider adapter. | Release data review. |
| T-020 | Operational traces expose hidden reasoning or document text. | Medium | Store concise decisions and evidence references, not private reasoning; redact payloads. | Trace schema and UI review. |

## 6. Upload security policy

- Allowed extensions: `.pdf`, `.txt`, `.md`, `.markdown`, `.html`, `.htm`.
- Maximum size: 25 MB.
- The declared MIME type must match the detected file type.
- Filenames are display metadata, never trusted paths.
- Storage keys use generated identifiers.
- Encrypted PDFs enter `quarantined` with a user-readable reason.
- Parsing has explicit wall-time and extracted-text limits.
- Archive formats and executable content are rejected.
- Raw HTML is parsed as text and never rendered unsanitized.
- A checksum is calculated before ingestion is accepted.

Antivirus scanning is not guaranteed by the selected free stack. The initial
release therefore never executes uploaded content and must document this residual
risk. A production infrastructure upgrade should add malware scanning.

## 7. Prompt-injection policy

- System and developer policies are authored server-side and versioned.
- Retrieved content is labeled as untrusted evidence.
- Evidence cannot add tools, change roles, modify limits, or request secrets.
- The model receives only tool schemas approved for the current node.
- Tool calls are independently authorized by server code.
- Retrieved instructions such as "ignore previous instructions" are treated as
  document claims, not commands.
- The reviewer checks suspicious instruction-like content and unsupported claims.
- Prompt-injection cases are mandatory release-gate evaluations.

## 8. Denial-of-service controls

- 25 MB upload limit.
- 100 documents and 10,000 active chunks per workspace.
- Three concurrent ingestion jobs per workspace.
- Two concurrent agent runs per user.
- Eight agent steps and two provider retries per run.
- Bounded parser output, prompt tokens, retrieved chunks, SSE lifetime, and trace size.
- PostgreSQL-backed rate counters for mutation and model endpoints.
- `429` responses include a safe retry time.
- Queue consumers use bounded batches and visibility timeouts.
- Provider quota exhaustion pauses new model work without corrupting jobs.

## 9. Secrets and logging

Never log:

- `Authorization` headers or JWTs.
- Supabase service-role credentials.
- Gemini API keys.
- Signed Storage URLs.
- Passwordless login tokens.
- Full document contents.
- Unredacted model prompts containing user documents.

Logs may include:

- Stable request, run, step, user, and workspace identifiers.
- Provider/model name, timing, token counts, status, and error class.
- Document and chunk identifiers.
- Sanitized policy decisions and evidence references.

## 10. Residual risks accepted for the free portfolio release

- Render cold starts and restarts reduce availability.
- Free services do not provide enterprise SLAs.
- Gemini free-tier processing is inappropriate for confidential production data.
- No malware-scanning service is included.
- Supabase free-tier backup and recovery guarantees are limited.
- PostgreSQL rate counters are less efficient than a dedicated distributed limiter.

The public deployment must use public, synthetic, or specifically approved demo
documents. These residual risks are not acceptable for confidential enterprise
deployment without an infrastructure and legal review.

## 11. Security release gates

- All RLS tables have positive and negative policy tests.
- Cross-tenant API, SSE, Storage, retrieval, and trace tests pass.
- No critical or high threat lacks an implemented control.
- Secret and dependency scans pass.
- Prompt-injection release suite passes.
- Approval race and idempotency tests pass.
- Logs and traces pass redaction review.
