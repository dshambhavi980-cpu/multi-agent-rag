export type RunStatus =
  | "accepted"
  | "running"
  | "awaiting_approval"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed"
  | "timed_out";

export type RunSummary = {
  id: string;
  conversation_id: string;
  question: string;
  status: RunStatus;
  mode: "simple" | "agentic";
  current_node: string | null;
  step_count: number;
  confidence: number | null;
  answer_status: "grounded" | "insufficient_evidence" | "failed" | null;
  output_message_id: string | null;
  approval_id: string | null;
  error: { code?: string; detail?: string; retryable?: boolean } | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type AgentStep = {
  id: string;
  step_number: number;
  node: string;
  status: "succeeded" | "failed" | "skipped";
  summary: string;
  duration_ms: number;
  created_at: string;
};

export type ToolCall = {
  id: string;
  tool_name: string;
  permission: string;
  status: "succeeded" | "failed";
  output_summary: Record<string, unknown>;
  duration_ms: number;
  created_at: string;
};

export type RunPageResult = { items: RunSummary[]; next_cursor: string | null };
export type RunTrace = { run: RunSummary; steps: AgentStep[]; tool_calls: ToolCall[] };

export type ObservabilityTrace = {
  request_id: string | null;
  trace_id: string;
  run_id: string;
  model: string;
  prompt_version: string;
  timings: Record<string, number>;
  input_tokens: number | null;
  output_tokens: number | null;
  token_usage_source: "provider" | "estimated" | null;
  replayed_from_run_id: string | null;
  replay_mode: "exact_snapshot" | "current_configuration" | null;
  error: { code?: string; detail?: string } | null;
  evidence: Array<{
    citation_id: string;
    document_id: string;
    label: string;
    page: number | null;
    section: string | null;
    quote: string;
    semantic_score: number | null;
    sparse_rank: number | null;
    rrf_score: number;
  }>;
  events: Array<{
    event_type: string;
    occurred_at: string;
    latency_ms: number | null;
    severity: "info" | "warning" | "error";
    attributes: Record<string, unknown>;
  }>;
};

export type WorkspaceObservability = {
  window_hours: number;
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  success_rate: number;
  p95_latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  active_runs: number;
  trace_count: number;
  trace_limit: number;
  retention_days: number;
};
