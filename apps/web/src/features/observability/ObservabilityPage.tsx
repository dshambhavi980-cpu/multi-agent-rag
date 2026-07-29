import { useQuery } from "@tanstack/react-query";
import { Activity, CircleAlert, Clock3, Database, RefreshCw, Zap } from "lucide-react";

import { requestJson } from "../../api/client";
import { useAuth } from "../auth/auth-context";
import type { WorkspaceObservability } from "../runs/runs.types";
import { useWorkspace } from "../workspaces/workspace-context";

export function ObservabilityPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const summary = useQuery({
    queryKey: ["observability", workspaceId],
    enabled: Boolean(session && workspaceId),
    queryFn: () =>
      requestJson<WorkspaceObservability>("/v1/observability/summary", {
        headers: {
          Authorization: `Bearer ${session?.access_token ?? ""}`,
          "X-Workspace-ID": workspaceId ?? "",
        },
      }),
    refetchInterval: 15_000,
  });
  const data = summary.data;
  const traceUsage = data ? Math.min((data.trace_count / data.trace_limit) * 100, 100) : 0;

  return (
    <section aria-labelledby="operations-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Health, latency, and quota</p>
          <h1 id="operations-title">Operations</h1>
        </div>
        <button
          className="icon-button bordered"
          type="button"
          aria-label="Refresh operations"
          title="Refresh operations"
          onClick={() => void summary.refetch()}
        >
          <RefreshCw size={18} />
        </button>
      </div>
      {summary.isError ? (
        <div className="inline-notice notice-error" role="alert">
          <CircleAlert size={18} /> Operational metrics could not be loaded.
        </div>
      ) : null}
      <div className="metric-grid">
        <article className="metric-panel">
          <Activity size={18} />
          <p>24h success rate</p>
          <strong>{data ? `${String(Math.round(data.success_rate * 100))}%` : "-"}</strong>
          <small>{data ? `${String(data.successful_runs)} of ${String(data.total_runs)} runs` : "Loading"}</small>
        </article>
        <article className="metric-panel">
          <Clock3 size={18} />
          <p>P95 latency</p>
          <strong>{data ? `${String(Math.round(data.p95_latency_ms))} ms` : "-"}</strong>
          <small>End-to-end execution</small>
        </article>
        <article className="metric-panel">
          <Zap size={18} />
          <p>Token volume</p>
          <strong>{data ? (data.input_tokens + data.output_tokens).toLocaleString() : "-"}</strong>
          <small>{data ? `${String(data.active_runs)} active runs` : "Loading"}</small>
        </article>
        <article className="metric-panel">
          <Database size={18} />
          <p>Detailed traces</p>
          <strong>{data ? `${String(data.trace_count)} / ${String(data.trace_limit)}` : "-"}</strong>
          <small>{data ? `${String(data.retention_days)} day retention` : "Loading"}</small>
        </article>
      </div>
      <section className="quota-band" aria-labelledby="trace-quota-title">
        <div>
          <h2 id="trace-quota-title">Trace storage</h2>
          <span>{Math.round(traceUsage)}%</span>
        </div>
        <progress value={traceUsage} max={100} aria-label="Trace storage quota" />
        <p>Detailed operational events are automatically trimmed to the newest 50 runs.</p>
      </section>
    </section>
  );
}
