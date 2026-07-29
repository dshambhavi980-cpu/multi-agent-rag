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
