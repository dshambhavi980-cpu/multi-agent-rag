export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "revision_requested"
  | "expired";

export type Approval = {
  id: string;
  run_id: string;
  status: ApprovalStatus;
  risk_level: "low" | "medium" | "high" | "critical";
  reasons: string[];
  proposed_output: string | null;
  reviewer_id: string | null;
  reviewer_comment: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ApprovalPageResult = {
  items: Approval[];
  next_cursor: string | null;
};
