import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Clock3,
  PencilLine,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { requestJson } from "../../api/client";
import { useAuth } from "../auth/auth-context";
import { useWorkspace } from "../workspaces/workspace-context";
import type {
  Approval,
  ApprovalPageResult,
  ApprovalStatus,
} from "./approval.types";

type Filter = "all" | ApprovalStatus;
type Decision = "approve" | "reject" | "revise";

export function ApprovalsPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [editedOutput, setEditedOutput] = useState("");
  const workspaceId = activeWorkspace?.id;
  const queryKey = ["approvals", workspaceId, filter];
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };

  const approvals = useQuery({
    queryKey,
    enabled: Boolean(session && workspaceId),
    queryFn: () => {
      const query = filter === "all" ? "" : `?status=${filter}`;
      return requestJson<ApprovalPageResult>(`/v1/approvals${query}`, { headers });
    },
  });

  const selected = useMemo(
    () =>
      approvals.data?.items.find((item) => item.id === selectedId) ??
      approvals.data?.items[0] ??
      null,
    [approvals.data?.items, selectedId],
  );

  const decide = useMutation({
    mutationFn: ({ action, item }: { action: Decision; item: Approval }) =>
      requestJson<Approval>(`/v1/approvals/${item.id}/${action}`, {
        method: "POST",
        headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(
          action === "approve"
            ? { comment, edited_output: editedOutput || null }
            : { comment },
        ),
      }),
    onSuccess: async () => {
      setSelectedId(null);
      await queryClient.invalidateQueries({ queryKey: ["approvals", workspaceId] });
    },
  });

  const canDecide = selected?.status === "pending" && comment.trim().length > 0;

  return (
    <section aria-labelledby="approvals-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Human oversight</p>
          <h1 id="approvals-title">Review queue</h1>
        </div>
        <button
          className="icon-button bordered"
          type="button"
          title="Refresh approvals"
          aria-label="Refresh approvals"
          onClick={() => void approvals.refetch()}
        >
          <RefreshCw size={18} />
        </button>
      </div>

      <div className="approval-toolbar">
        <div className="segmented-control" aria-label="Approval status">
          {(["pending", "all", "approved", "rejected"] as const).map((status) => (
            <button
              key={status}
              type="button"
              aria-pressed={filter === status}
              onClick={() => {
                setFilter(status);
                setSelectedId(null);
              }}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
        <span className="memory-count">
          {approvals.data?.items.length ?? 0} requests
        </span>
      </div>

      {approvals.isLoading ? <p className="table-message">Loading reviews...</p> : null}
      {approvals.isError ? (
        <p className="table-message">The review queue could not be loaded.</p>
      ) : null}
      {!approvals.isLoading && !approvals.data?.items.length ? (
        <div className="memory-empty">
          <ShieldAlert size={25} aria-hidden="true" />
          <p>No approval requests match this view.</p>
        </div>
      ) : null}

      {approvals.data?.items.length ? (
        <div className="approval-workspace">
          <div className="approval-list" aria-label="Approval requests">
            {approvals.data.items.map((item) => (
              <button
                className={
                  selected?.id === item.id
                    ? "approval-list-item approval-list-item-active"
                    : "approval-list-item"
                }
                key={item.id}
                type="button"
                onClick={() => {
                  setSelectedId(item.id);
                  setComment("");
                  setEditedOutput(item.proposed_output ?? "");
                }}
              >
                <span className={`risk-dot risk-${item.risk_level}`} aria-hidden="true" />
                <span>
                  <strong>{item.risk_level} risk</strong>
                  <small>{item.reasons[0]}</small>
                </span>
                <time dateTime={item.created_at}>
                  {new Date(item.created_at).toLocaleDateString()}
                </time>
              </button>
            ))}
          </div>

          {selected ? (
            <div className="approval-detail">
              <div className="approval-detail-heading">
                <div>
                  <span className={`status-badge approval-${selected.status}`}>
                    {selected.status.replace("_", " ")}
                  </span>
                  <h2>Run {selected.run_id.slice(0, 8)}</h2>
                </div>
                <span className="approval-age">
                  <Clock3 size={15} />
                  {new Date(selected.created_at).toLocaleString()}
                </span>
              </div>

              <div className="approval-reasons">
                <h3>Why review is required</h3>
                <ul>
                  {selected.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
              </div>

              <label className="approval-field">
                <span><PencilLine size={15} /> Proposed output</span>
                <textarea
                  value={editedOutput || selected.proposed_output || ""}
                  readOnly={selected.status !== "pending"}
                  rows={9}
                  onChange={(event) => {
                    setEditedOutput(event.target.value);
                  }}
                />
              </label>

              {selected.status === "pending" ? (
                <>
                  <label className="approval-field">
                    <span>Reviewer comment</span>
                    <textarea
                      value={comment}
                      rows={3}
                      maxLength={2000}
                      placeholder="Record the reason for this decision"
                      onChange={(event) => {
                        setComment(event.target.value);
                      }}
                    />
                  </label>
                  <div className="approval-actions">
                    <button
                      className="decision-button decision-approve"
                      type="button"
                      disabled={!canDecide || decide.isPending}
                      onClick={() => {
                        decide.mutate({ action: "approve", item: selected });
                      }}
                    >
                      <Check size={17} /> Approve
                    </button>
                    <button
                      className="decision-button"
                      type="button"
                      disabled={!canDecide || decide.isPending}
                      onClick={() => {
                        decide.mutate({ action: "revise", item: selected });
                      }}
                    >
                      <RotateCcw size={17} /> Request revision
                    </button>
                    <button
                      className="decision-button decision-reject"
                      type="button"
                      disabled={!canDecide || decide.isPending}
                      onClick={() => {
                        decide.mutate({ action: "reject", item: selected });
                      }}
                    >
                      <X size={17} /> Reject
                    </button>
                  </div>
                </>
              ) : (
                <p className="approval-audit">
                  {selected.reviewer_comment ?? "Decision recorded without a comment."}
                </p>
              )}
              {decide.isError ? (
                <p className="form-message form-error" role="alert">
                  The decision could not be recorded.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
