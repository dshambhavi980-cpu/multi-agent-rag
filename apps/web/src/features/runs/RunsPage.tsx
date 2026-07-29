import { useVirtualizer } from "@tanstack/react-virtual";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  Clock3,
  RefreshCw,
  RotateCcw,
  Search,
  Wrench,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { requestJson } from "../../api/client";
import { useAuth } from "../auth/auth-context";
import { useWorkspace } from "../workspaces/workspace-context";
import type { ObservabilityTrace, RunPageResult, RunTrace } from "./runs.types";

export function RunsPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [replayMode, setReplayMode] = useState<"exact_snapshot" | "current_configuration">(
    "current_configuration",
  );
  const [replayReason, setReplayReason] = useState("Investigate this run");
  const queryClient = useQueryClient();
  const workspaceId = activeWorkspace?.id;
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };
  const runs = useQuery({
    queryKey: ["runs", workspaceId],
    enabled: Boolean(session && workspaceId),
    queryFn: () => requestJson<RunPageResult>("/v1/runs?limit=100", { headers }),
    refetchInterval: (query) =>
      query.state.data?.items.some((run) =>
        ["accepted", "running", "awaiting_approval", "cancelling"].includes(run.status),
      )
        ? 2_000
        : false,
  });
  const activeId =
    runs.data?.items.find((run) => run.id === selectedId)?.id ??
    runs.data?.items[0]?.id ??
    null;
  const trace = useQuery({
    queryKey: ["run-trace", workspaceId, activeId],
    enabled: Boolean(session && workspaceId && activeId),
    queryFn: () =>
      requestJson<RunTrace>(`/v1/runs/${activeId ?? ""}/trace`, { headers }),
    refetchInterval: ["accepted", "running"].includes(
      runs.data?.items.find((run) => run.id === activeId)?.status ?? "",
    )
      ? 2_000
      : false,
  });
  const diagnostics = useQuery({
    queryKey: ["run-observability", workspaceId, activeId],
    enabled: Boolean(session && workspaceId && activeId),
    queryFn: () =>
      requestJson<ObservabilityTrace>(`/v1/runs/${activeId ?? ""}/observability`, {
        headers,
      }),
    refetchInterval: ["accepted", "running"].includes(
      runs.data?.items.find((run) => run.id === activeId)?.status ?? "",
    )
      ? 2_000
      : false,
  });
  const replay = useMutation({
    mutationFn: () =>
      requestJson(`/v1/runs/${activeId ?? ""}/replay`, {
        method: "POST",
        headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ mode: replayMode, reason: replayReason.trim() }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["runs", workspaceId] });
    },
  });
  const timeline = useMemo(
    () => [
      ...(trace.data?.steps.map((step) => ({ kind: "step" as const, ...step })) ?? []),
      ...(trace.data?.tool_calls.map((tool) => ({ kind: "tool" as const, ...tool })) ?? []),
    ].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [trace.data],
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  // React Compiler intentionally leaves TanStack Virtual's imperative API alone.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: timeline.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 92,
    overscan: 6,
    initialRect: { width: 700, height: 350 },
  });
  const measuredTimeline = virtualizer.getVirtualItems();
  const timelineRows = measuredTimeline.length
    ? measuredTimeline
    : timeline.slice(0, 12).map((item, index) => ({
        index,
        key: item.id,
        start: index * 92,
      }));
  const selected = trace.data?.run;

  return (
    <section aria-labelledby="runs-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Inspectable execution</p>
          <h1 id="runs-title">Agent runs</h1>
        </div>
        <button
          className="icon-button bordered"
          type="button"
          aria-label="Refresh runs"
          title="Refresh runs"
          onClick={() => void runs.refetch()}
        >
          <RefreshCw size={18} />
        </button>
      </div>

      {runs.isLoading ? <p className="table-message">Loading runs...</p> : null}
      {runs.isError ? (
        <div className="inline-notice notice-error" role="alert">
          <CircleAlert size={18} /> Run history could not be loaded.
        </div>
      ) : null}
      {!runs.isLoading && !runs.data?.items.length ? (
        <div className="memory-empty">
          <Bot size={25} />
          <p>No runs have been started in this workspace.</p>
        </div>
      ) : null}

      {runs.data?.items.length ? (
        <div className="run-workspace">
          <div className="run-list" aria-label="Recent runs">
            {runs.data.items.map((run) => (
              <button
                type="button"
                key={run.id}
                className={activeId === run.id ? "run-list-item run-list-active" : "run-list-item"}
                onClick={() => {
                  setSelectedId(run.id);
                }}
              >
                <span className={`run-status-dot run-${run.status}`} />
                <span>
                  <strong>{run.question}</strong>
                  <small>{run.mode} · {run.status.replace("_", " ")}</small>
                </span>
                <time>{new Date(run.created_at).toLocaleDateString()}</time>
              </button>
            ))}
          </div>
          <div className="run-detail">
            {selected ? (
              <>
                <div className="run-summary">
                  <div>
                    <span className={`status-badge approval-${selected.status}`}>
                      {selected.status.replace("_", " ")}
                    </span>
                    <h2>{selected.question}</h2>
                  </div>
                  <dl>
                    <div><dt>Mode</dt><dd>{selected.mode}</dd></div>
                    <div><dt>Steps</dt><dd>{selected.step_count}</dd></div>
                    <div>
                      <dt>Confidence</dt>
                      <dd>
                        {selected.confidence === null
                          ? "-"
                          : `${String(Math.round(selected.confidence * 100))}%`}
                      </dd>
                    </div>
                  </dl>
                </div>
                {selected.error?.detail ? (
                  <div className="inline-notice notice-error">
                    <CircleAlert size={18} /> {selected.error.detail}
                  </div>
                ) : null}
                {diagnostics.data?.trace_id ? (
                  <div className="trace-diagnostics">
                    <dl className="trace-facts">
                      <div><dt>Trace ID</dt><dd title={diagnostics.data.trace_id}>{diagnostics.data.trace_id.slice(0, 8)}</dd></div>
                      <div><dt>Total latency</dt><dd>{Math.round(diagnostics.data.timings.total_ms ?? 0)} ms</dd></div>
                      <div><dt>Tokens</dt><dd>{(diagnostics.data.input_tokens ?? 0) + (diagnostics.data.output_tokens ?? 0)}</dd></div>
                      <div><dt>Evidence</dt><dd>{diagnostics.data.evidence.length}</dd></div>
                    </dl>
                    {diagnostics.data.evidence.length ? (
                      <div className="trace-evidence">
                        <h3>Retrieval evidence</h3>
                        {diagnostics.data.evidence.map((item) => (
                          <article key={item.citation_id}>
                            <strong>{item.citation_id} · {item.label}</strong>
                            <p>{item.quote}</p>
                          </article>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <h3 className="timeline-title">Execution timeline</h3>
                <div className="timeline-scroll" ref={scrollRef}>
                  {!timeline.length ? (
                    <p className="table-message">No agent trace for this fast RAG run.</p>
                  ) : (
                    <div
                      className="timeline-virtual"
                      style={{ height: `${String(virtualizer.getTotalSize())}px` }}
                    >
                      {timelineRows.map((virtualItem) => {
                        const item = timeline[virtualItem.index];
                        if (!item) return null;
                        return (
                          <article
                            className="timeline-item"
                            key={item.id}
                            style={{ transform: `translateY(${String(virtualItem.start)}px)` }}
                          >
                            <span className="timeline-icon">
                              {item.kind === "tool" ? <Wrench size={16} /> :
                                item.status === "failed" ? <CircleAlert size={16} /> :
                                <CheckCircle2 size={16} />}
                            </span>
                            <div>
                              <strong>
                                {item.kind === "tool" ? item.tool_name : item.node}
                              </strong>
                              <p>
                                {item.kind === "tool"
                                  ? `Permission: ${item.permission}`
                                  : item.summary}
                              </p>
                            </div>
                            <span className="timeline-duration">
                              <Clock3 size={13} /> {Math.round(item.duration_ms)} ms
                            </span>
                          </article>
                        );
                      })}
                    </div>
                  )}
                </div>
                <p className="trace-privacy">
                  <Search size={14} /> Trace shows decisions and tool outcomes only. Secrets and
                  full document content are excluded.
                </p>
                {["completed", "failed", "cancelled", "timed_out"].includes(selected.status) ? (
                  <form
                    className="replay-panel"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (replayReason.trim()) {
                        replay.mutate();
                      }
                    }}
                  >
                    <div className="replay-heading">
                      <h3><RotateCcw size={16} /> Replay run</h3>
                      <div className="segmented-control" aria-label="Replay mode">
                        <button
                          type="button"
                          aria-pressed={replayMode === "current_configuration"}
                          onClick={() => {
                            setReplayMode("current_configuration");
                          }}
                        >
                          Current
                        </button>
                        <button
                          type="button"
                          aria-pressed={replayMode === "exact_snapshot"}
                          onClick={() => {
                            setReplayMode("exact_snapshot");
                          }}
                        >
                          Exact
                        </button>
                      </div>
                    </div>
                    <label>
                      Replay reason
                      <input
                        value={replayReason}
                        maxLength={500}
                        onChange={(event) => {
                          setReplayReason(event.target.value);
                        }}
                      />
                    </label>
                    <button
                      className="primary-button"
                      type="submit"
                      disabled={replay.isPending || !replayReason.trim()}
                    >
                      <RotateCcw size={16} /> {replay.isPending ? "Starting..." : "Start replay"}
                    </button>
                    {replay.isError ? <p className="field-error" role="alert">Replay could not be started.</p> : null}
                  </form>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
