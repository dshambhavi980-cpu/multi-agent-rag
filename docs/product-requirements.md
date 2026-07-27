# Product Requirements

Status: Approved Phase 0 baseline  
Version: 0.1.0  
Last updated: 2026-07-27

## 1. Product statement

The product is a multi-tenant knowledge assistant that answers questions and
completes bounded research tasks using evidence from user-uploaded documents.
It combines hybrid retrieval, grounded generation, multi-agent orchestration,
memory, human approval, and inspectable execution traces.

The first release is a publicly hosted portfolio system built with free service
tiers. Its engineering practices must support a future production deployment
without rewriting domain logic.

## 2. Target users

### Primary user: knowledge worker

A developer, analyst, support specialist, or operations professional who needs
fast answers from a small collection of internal technical documents.

Needs:

- Upload and organize documents.
- Ask factual and multi-document questions.
- Verify answers by opening exact evidence.
- Understand when the system lacks evidence.

### Secondary user: reviewer

A subject-matter expert who reviews uncertain, sensitive, or low-confidence
outputs.

Needs:

- See why a run was escalated.
- Inspect evidence and the proposed answer.
- Approve, edit, reject, or request revision.
- Audit earlier decisions.

### Administrative user: workspace owner

The person responsible for membership, documents, limits, and workspace policy.

Needs:

- Manage workspace members and roles.
- Delete documents and remembered information.
- Configure approval and retention policies.
- Inspect usage and operational health.

## 3. Release scope

### In scope

- Email-based authentication through Supabase Auth.
- Isolated workspaces with owner, reviewer, and member roles.
- PDF, TXT, Markdown, and HTML ingestion.
- Maximum upload size of 25 MB per file.
- Hybrid semantic and PostgreSQL full-text retrieval.
- Streamed grounded answers with exact citations.
- Simple-RAG and bounded multi-agent execution paths.
- Conversation history and attributable long-term memory.
- Human approval with durable pause and resume.
- Document, trace, review, evaluation, memory, and settings screens.
- Structured operational traces and replay.
- Public deployment on Cloudflare Pages, Render, and Supabase.

### Out of scope for the first release

- Autonomous email, financial, deletion, or external-system actions.
- OCR for image-only PDFs.
- Audio, video, spreadsheet, and image ingestion.
- Internet search as an agent tool.
- Anonymous document uploads.
- Enterprise SSO, SCIM, legal hold, and compliance certification.
- Guaranteed 24/7 availability on free infrastructure.
- Unbounded autonomous agents.

## 4. Roles and permissions

| Capability | Owner | Reviewer | Member |
|---|:---:|:---:|:---:|
| View workspace documents | Yes | Yes | Yes |
| Upload documents | Yes | Yes | Yes |
| Delete own uploaded document | Yes | Yes | Yes |
| Delete any workspace document | Yes | No | No |
| Ask questions and create runs | Yes | Yes | Yes |
| View own run traces | Yes | Yes | Yes |
| View all workspace traces | Yes | Yes | No |
| Decide approval requests | Yes | Yes | No |
| Manage member roles | Yes | No | No |
| Configure workspace policy | Yes | No | No |
| Delete workspace | Yes | No | No |

Workspace membership is the authorization boundary. A user may belong to more
than one workspace, but every request must select exactly one active workspace.

## 5. Data ownership

- A workspace owns its documents, chunks, shared memories, runs, approvals,
  evaluation records, and audit events.
- A user owns personal preferences and private memories.
- Conversation ownership belongs to the creating user within a workspace.
- Workspace owners may delete workspace-owned data.
- Reviewers may inspect workspace runs and approvals but may not manage members.
- Service providers process data only as infrastructure dependencies; they do
  not become application owners.
- No tenant-owned record may exist without a `workspace_id`, except a user's
  global profile and provider-independent system metadata.

## 6. Sensitive actions and approval policy

The initial tool set is read-only, except for application-owned data management.
The following actions require human approval:

- A final answer with confidence below 0.65.
- A final answer whose citation coverage is below 0.90.
- A final answer containing unresolved conflicting evidence.
- Publishing or exporting a generated report outside the application.
- Creating, updating, or deleting shared long-term memory.
- Deleting a document that was not uploaded by the requesting user.
- Replaying a run that previously reached an approval node.
- Any future external side-effecting tool.

The following actions are always denied in the first release:

- Financial transactions.
- Sending email or messages.
- Executing arbitrary shell commands.
- Modifying third-party systems.
- Deleting an entire workspace through an agent.

## 7. Functional requirements

### Identity and tenancy

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-001 | Users can authenticate and sign out. | A valid session grants access; expired or invalid tokens return `401`. |
| FR-002 | Every tenant request is scoped to one workspace. | Cross-workspace read and write tests return no data or `403`. |
| FR-003 | Owners can manage workspace membership and roles. | Only an owner can add, remove, or change a member role. |

### Documents and ingestion

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-010 | Users can upload PDF, TXT, Markdown, and HTML files. | A valid file up to 25 MB reaches `ready` or a documented failure state. |
| FR-011 | Uploads are direct to object storage. | File bytes do not pass through the FastAPI process. |
| FR-012 | Ingestion is durable and idempotent. | Retrying the same checksum does not duplicate documents or chunks. |
| FR-013 | Users can inspect ingestion progress and failures. | Status and progress update without a full page refresh. |
| FR-014 | Authorized users can delete documents. | The source, chunks, caches, and search visibility are removed consistently. |

### Retrieval and answers

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-020 | The system performs semantic and keyword retrieval. | Each trace records dense rank, sparse rank, and fused rank. |
| FR-021 | Retrieval is restricted before ranking. | No candidate from another workspace enters a retrieval trace. |
| FR-022 | Answers stream to the browser. | The UI displays tokens before the generation request completes. |
| FR-023 | Every factual answer contains resolvable citations. | Every returned citation maps to a supplied chunk, document, and page or section. |
| FR-024 | Unsupported questions fail safely. | Missing evidence returns `insufficient_evidence` without fabricated citations. |
| FR-025 | Users can inspect source evidence. | Selecting a citation opens the exact source location and highlighted chunk. |

### Agents and memory

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-030 | Simple questions use the simple-RAG path. | Router tests send lookup questions through one bounded answer path. |
| FR-031 | Complex questions can use a multi-agent graph. | A synthesis case produces a plan, retrieval steps, review, and final answer. |
| FR-032 | Agent execution is bounded. | Every run respects configured step, token, retry, and wall-time limits. |
| FR-033 | Runs are resumable. | A process restart can resume from the latest durable checkpoint. |
| FR-034 | Memory is attributable and deletable. | Each memory exposes source, confidence, visibility, and delete control. |

### Approval, traces, and evaluation

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-040 | Sensitive runs pause for approval. | The graph cannot continue until an authorized decision is recorded. |
| FR-041 | Reviewers can approve, edit, reject, or request revision. | Each action produces one immutable audit record and one state transition. |
| FR-042 | Users can inspect execution traces. | A trace shows routing, tools, retrieval evidence, timing, and errors. |
| FR-043 | Replay is controlled. | Replay never repeats a sensitive action without a new approval. |
| FR-044 | Evaluations compare retrieval and workflow variants. | The dashboard reports retrieval, citation, quality, latency, and usage metrics. |

## 8. Non-functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| NFR-001 | Warm-path performance follows the approved budget. | Phase 13 tests meet the p50 and p95 targets in the performance budget. |
| NFR-002 | Cold starts are represented honestly. | The UI detects startup and never reports cold latency as warm latency. |
| NFR-003 | Tenant data is isolated at database and API layers. | Automated negative authorization and RLS tests pass. |
| NFR-004 | Secrets remain server-side. | Repository and frontend bundle scans find no private credentials. |
| NFR-005 | External failures degrade safely. | Timeout, quota, and provider failures produce typed retryable or terminal errors. |
| NFR-006 | All mutating operations are idempotent where duplication is harmful. | Duplicate-key tests produce one logical operation. |
| NFR-007 | Operational records are privacy-aware and bounded. | Logs are redacted and retention cleanup keeps storage within its budget. |
| NFR-008 | Accessibility meets WCAG 2.2 AA for core workflows. | Automated checks and keyboard tests pass for upload, chat, and approval. |
| NFR-009 | The deployment is reproducible. | A clean environment can be created from migrations and documented configuration. |

## 9. Product success measures

- At least 95% citation precision on the reviewed evaluation set.
- Hybrid retrieval improves nDCG@10 over dense-only retrieval by at least 10%.
- At least 90% of answerable evaluation questions return the expected evidence.
- Unsupported questions avoid fabricated citations in 100% of release-gate cases.
- Warm-path simple-answer p95 completes within 10 seconds.
- No cross-tenant access succeeds in automated security tests.
- At least 95% of ingestion jobs complete without manual recovery on valid files.

## 10. Product defaults

- Maximum document size: 25 MB.
- Maximum documents per workspace: 100.
- Maximum active chunks per workspace: 10,000.
- Maximum retrieved chunks per answer: 10.
- Default final evidence count: 6.
- Maximum agent steps: 8.
- Maximum concurrent agent runs per user: 2.
- Approval confidence threshold: 0.65.
- Approval citation-coverage threshold: 0.90.
- Detailed trace retention: 50 runs per workspace or 30 days, whichever is lower.

These are defensive free-tier defaults. They are configuration values and must
be changed only after capacity and evaluation testing.
