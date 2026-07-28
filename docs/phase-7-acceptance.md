# Phase 7 Acceptance: Multi-Agent Orchestration

## Delivered behavior

Phase 7 introduces a deterministic complexity router in front of the existing
grounded RAG service. Explicit `simple` requests and ordinary lookup questions
continue through the Phase 6 path. Comparison, reconciliation, multi-question,
and explicitly `agentic` requests enter a typed LangGraph workflow.

The graph contains six bounded nodes: supervisor, planner, retrieval, synthesis,
writer, and reviewer. Planner output and tool inputs are validated with Pydantic.
Independent retrieval subtasks run concurrently through one allow-listed,
read-only hybrid-search tool. The writer receives document chunks inside explicit
`untrusted_evidence` boundaries, and the reviewer rejects uncited claims or
unknown citation identifiers before output is published.

## Durability and budgets

Every completed node stores an `agent_steps` record and replaces the run's
`workflow_checkpoints` snapshot transactionally. Failed tool calls record only a
sanitized query hash, input size, filter count, result count, timing, and error
code. Raw queries, document text, prompts, credentials, and hidden reasoning are
not written to tool logs.

Agent runs are limited to eight graph steps, three retrieval subtasks, three
concurrent searches, a 60-second wall-clock deadline, and fixed context/output
budgets. Cancellation is checked at every node boundary. The authenticated
`POST /v1/runs/{run_id}/resume` operation reloads the latest durable state and
starts directly at its recorded next node.

## Verification

- Backend: 91 tests pass with 90.83% line coverage before the resume-route test.
- Static analysis: Ruff and strict mypy pass for the API application.
- Routing tests prove simple requests avoid the graph and complex requests enter it.
- Graph tests cover parallel retrieval, six-node completion, step/time budgets,
  controlled provider failure, checkpoint resume, deny-by-default tools,
  sanitized logs, and malicious document instructions.
- Contracts: 30 OpenAPI paths and 3 AsyncAPI channels validate.
- Migration history includes the Phase 7 orchestration schema and RPC boundary.

## Exit criteria mapping

| Criterion | Evidence |
| --- | --- |
| Simple requests avoid graph latency | Deterministic router tests and unchanged simple executor |
| Agent runs terminate within budgets | Step, recursion, wall-time, context, output, and concurrency limits |
| Failed nodes are controlled | Typed `ApplicationError`, durable failed step, terminal run state |
| Graph resumes from durable state | Checkpoint-after-node persistence and resume integration test |

The public Vercel deployment still hosts only the frontend. Agentic execution
becomes publicly usable after the FastAPI service and this migration are deployed.

