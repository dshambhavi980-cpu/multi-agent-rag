import { useQuery } from "@tanstack/react-query";
import { BarChart3, CircleAlert, RefreshCw } from "lucide-react";

import { ApiClientError, requestJson } from "../../api/client";
import { useAuth } from "../auth/auth-context";
import { useWorkspace } from "../workspaces/workspace-context";

type Evaluation = {
  id: string;
  suite: string;
  variants: string[];
  status: string;
  case_count: number;
  metrics?: Record<string, number>;
  created_at: string;
};
type EvaluationPageResult = { items: Evaluation[]; next_cursor: string | null };

export function EvaluationsPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const evaluations = useQuery({
    queryKey: ["evaluations", workspaceId],
    enabled: Boolean(session && workspaceId),
    retry: false,
    queryFn: () =>
      requestJson<EvaluationPageResult>("/v1/evaluations", {
        headers: {
          Authorization: `Bearer ${session?.access_token ?? ""}`,
          "X-Workspace-ID": workspaceId ?? "",
        },
      }),
  });
  const unavailable =
    evaluations.error instanceof ApiClientError && evaluations.error.status === 404;

  return (
    <section aria-labelledby="evaluations-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Quality assurance</p>
          <h1 id="evaluations-title">Evaluations</h1>
        </div>
        <button
          className="icon-button bordered"
          type="button"
          aria-label="Refresh evaluations"
          onClick={() => void evaluations.refetch()}
        >
          <RefreshCw size={18} />
        </button>
      </div>
      {evaluations.isLoading ? <p className="table-message">Loading evaluations...</p> : null}
      {unavailable ? (
        <div className="inline-notice notice-warning" role="status">
          <CircleAlert size={18} />
          <span>Evaluation execution is not enabled in this deployment.</span>
        </div>
      ) : null}
      {evaluations.isError && !unavailable ? (
        <div className="inline-notice notice-error" role="alert">
          <CircleAlert size={18} /> Evaluations could not be loaded.
        </div>
      ) : null}
      {!evaluations.isLoading && !evaluations.isError && !evaluations.data?.items.length ? (
        <div className="memory-empty">
          <BarChart3 size={25} />
          <p>No evaluation runs in this workspace.</p>
        </div>
      ) : null}
      <div className="evaluation-grid">
        {(evaluations.data?.items ?? []).map((evaluation) => (
          <article className="evaluation-row" key={evaluation.id}>
            <div>
              <strong>{evaluation.suite}</strong>
              <p>{evaluation.variants.join(", ")}</p>
            </div>
            <span className="status-badge">{evaluation.status}</span>
            <span>{evaluation.case_count} cases</span>
            <time>{new Date(evaluation.created_at).toLocaleDateString()}</time>
          </article>
        ))}
      </div>
    </section>
  );
}
