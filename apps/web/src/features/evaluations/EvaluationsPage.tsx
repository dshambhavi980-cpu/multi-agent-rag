import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  CheckCircle2,
  CircleAlert,
  FlaskConical,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";

import { ApiClientError, requestJson } from "../../api/client";
import { useAuth } from "../auth/auth-context";
import { useWorkspace } from "../workspaces/workspace-context";

type Variant =
  | "keyword_only"
  | "dense_only"
  | "hybrid"
  | "simple_rag"
  | "agentic";
type EvaluationResult = {
  id: string;
  case_id: string;
  category: string;
  variant: Variant;
  status: "passed" | "failed" | "error";
  metrics: Record<string, number>;
  latency_ms: number;
  model_calls: number;
  prompt_tokens: number;
  output_tokens: number;
  failure_code: string | null;
  created_at: string;
};
type Evaluation = {
  id: string;
  suite: string;
  suite_version: number;
  variants: Variant[];
  status: string;
  case_count: number;
  metrics: Record<string, number>;
  gate_passed: boolean | null;
  gate_failures: string[];
  created_at: string;
  completed_at: string | null;
  results: EvaluationResult[];
};
type EvaluationPageResult = { items: Evaluation[]; next_cursor: string | null };
type SuiteSummary = {
  suite: string;
  version: number;
  reviewed_by: string;
  reviewed_at: string;
  case_count: number;
  categories: Record<string, number>;
  thresholds: Record<string, number>;
};

const variants: Array<{ id: Variant; label: string; cost: string }> = [
  { id: "keyword_only", label: "Keyword", cost: "No model generation" },
  { id: "dense_only", label: "Dense", cost: "Embedding only" },
  { id: "hybrid", label: "Hybrid", cost: "Embedding only" },
  { id: "simple_rag", label: "Simple RAG", cost: "Uses Gemini quota" },
  { id: "agentic", label: "Agentic", cost: "Uses more Gemini quota" },
];

function percent(value: number | undefined) {
  return `${String(Math.round((value ?? 0) * 100))}%`;
}

export function EvaluationsPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedVariants, setSelectedVariants] = useState<Variant[]>([
    "keyword_only",
    "dense_only",
    "hybrid",
  ]);
  const [maxCases, setMaxCases] = useState(10);
  const workspaceId = activeWorkspace?.id;
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };
  const suite = useQuery({
    queryKey: ["evaluation-suite", workspaceId],
    enabled: Boolean(session && workspaceId),
    retry: false,
    queryFn: () => requestJson<SuiteSummary>("/v1/evaluations/suite", { headers }),
  });
  const evaluations = useQuery({
    queryKey: ["evaluations", workspaceId],
    enabled: Boolean(session && workspaceId),
    retry: false,
    queryFn: () =>
      requestJson<EvaluationPageResult>("/v1/evaluations?limit=50", { headers }),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => ["queued", "running"].includes(item.status))
        ? 2_000
        : false,
  });
  const activeId =
    evaluations.data?.items.find((item) => item.id === selectedId)?.id ??
    evaluations.data?.items[0]?.id ??
    null;
  const detail = useQuery({
    queryKey: ["evaluation", workspaceId, activeId],
    enabled: Boolean(session && workspaceId && activeId),
    queryFn: () =>
      requestJson<Evaluation>(`/v1/evaluations/${activeId ?? ""}`, { headers }),
    refetchInterval: ["queued", "running"].includes(
      evaluations.data?.items.find((item) => item.id === activeId)?.status ?? "",
    )
      ? 2_000
      : false,
  });
  const create = useMutation({
    mutationFn: () =>
      requestJson<Evaluation>("/v1/evaluations", {
        method: "POST",
        headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          suite: "phase12-reviewed-v1",
          variants: selectedVariants,
          max_cases: maxCases,
        }),
      }),
    onSuccess: async (created) => {
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["evaluations", workspaceId] });
    },
  });
  const unavailable =
    evaluations.error instanceof ApiClientError && evaluations.error.status === 404;
  const selected = detail.data;

  return (
    <section aria-labelledby="evaluations-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Measured release quality</p>
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

      {suite.data?.case_count ? (
        <div className="evaluation-suite-band">
          <FlaskConical size={19} />
          <div>
            <strong>{suite.data.suite}</strong>
            <p>
              {suite.data.case_count} reviewed cases · version {suite.data.version} ·
              citation gate {percent(suite.data.thresholds.citation_precision)}
            </p>
          </div>
          <span><ShieldCheck size={15} /> Reviewed</span>
        </div>
      ) : null}

      <form
        className="evaluation-launcher"
        onSubmit={(event) => {
          event.preventDefault();
          if (selectedVariants.length) create.mutate();
        }}
      >
        <div className="evaluation-launcher-intro">
          <h2>Run comparison</h2>
          <p>Retrieval modes are inexpensive. Answer modes consume free Gemini quota.</p>
        </div>
        <fieldset>
          <legend>Variants</legend>
          <div className="evaluation-variants">
            {variants.map((variant) => (
              <label key={variant.id}>
                <input
                  type="checkbox"
                  checked={selectedVariants.includes(variant.id)}
                  onChange={(event) => {
                    setSelectedVariants((current) =>
                      event.target.checked
                        ? [...current, variant.id]
                        : current.filter((item) => item !== variant.id),
                    );
                  }}
                />
                <span><strong>{variant.label}</strong><small>{variant.cost}</small></span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="evaluation-run-controls">
          <label className="evaluation-case-count">
            Cases
            <input
              type="number"
              min={1}
              max={50}
              value={maxCases}
              onChange={(event) => {
                setMaxCases(Math.min(50, Math.max(1, Number(event.target.value))));
              }}
            />
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={!selectedVariants.length || create.isPending}
          >
            <Play size={16} /> {create.isPending ? "Starting..." : "Run evaluation"}
          </button>
        </div>
        {create.isError ? (
          <p className="field-error" role="alert">Evaluation could not be started.</p>
        ) : null}
      </form>

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

      {evaluations.data?.items.length ? (
        <div className="evaluation-workspace">
          <div className="evaluation-grid" aria-label="Evaluation runs">
            {evaluations.data.items.map((evaluation) => (
              <button
                type="button"
                className={
                  activeId === evaluation.id
                    ? "evaluation-row evaluation-row-active"
                    : "evaluation-row"
                }
                key={evaluation.id}
                onClick={() => {
                  setSelectedId(evaluation.id);
                }}
              >
                <div>
                  <strong>{evaluation.suite}</strong>
                  <p>{evaluation.variants.join(", ")}</p>
                </div>
                <span className="status-badge">{evaluation.status}</span>
                <span>{evaluation.case_count} cases</span>
                <time>{new Date(evaluation.created_at).toLocaleDateString()}</time>
              </button>
            ))}
          </div>
          <div className="evaluation-detail">
            {selected ? (
              <>
                <div className="evaluation-detail-heading">
                  <div>
                    <p className="eyebrow">Release gate</p>
                    <h2>{selected.gate_passed === null ? selected.status : selected.gate_passed ? "Passed" : "Blocked"}</h2>
                  </div>
                  {selected.gate_passed ? <CheckCircle2 size={23} /> : <CircleAlert size={23} />}
                </div>
                <div className="evaluation-metrics">
                  <div><span>Hybrid nDCG</span><strong>{percent(selected.metrics.hybrid_ndcg)}</strong></div>
                  <div><span>Dense nDCG</span><strong>{percent(selected.metrics.dense_only_ndcg)}</strong></div>
                  <div><span>Citation precision</span><strong>{percent(selected.metrics.citation_precision)}</strong></div>
                  <div><span>Critical safety</span><strong>{percent(selected.metrics.critical_safety_pass_rate)}</strong></div>
                  <div><span>P95 latency</span><strong>{Math.round(selected.metrics.p95_latency_ms ?? 0)} ms</strong></div>
                  <div><span>Failure rate</span><strong>{percent(selected.metrics.failure_rate)}</strong></div>
                </div>
                {selected.gate_failures.length ? (
                  <div className="inline-notice notice-error">
                    <CircleAlert size={17} /> Blocked by: {selected.gate_failures.join(", ")}
                  </div>
                ) : null}
                <h3>Case results</h3>
                <div className="evaluation-results">
                  {selected.results.slice(0, 100).map((result) => (
                    <div key={result.id}>
                      <span className={`run-status-dot run-${result.status}`} />
                      <strong>{result.case_id}</strong>
                      <span>{result.variant}</span>
                      <time>{Math.round(result.latency_ms)} ms</time>
                    </div>
                  ))}
                  {!selected.results.length ? (
                    <p className="table-message">Results appear as the run progresses.</p>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
