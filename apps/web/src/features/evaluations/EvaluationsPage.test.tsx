import { fireEvent, screen, waitFor } from "@testing-library/react";

import { ApiClientError } from "../../api/client";
import { renderWithProviders } from "../../test/render";
import { EvaluationsPage } from "./EvaluationsPage";

const mocks = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("../../api/client", () => {
  class MockApiClientError extends Error {
    constructor(
      message: string,
      readonly status: number,
    ) {
      super(message);
    }
  }
  return { ApiClientError: MockApiClientError, requestJson: mocks.requestJson };
});
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({ session: { access_token: "token" } }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "workspace-1" } }),
}));

const evaluation = {
  id: "evaluation-1",
  suite: "phase12-reviewed-v1",
  suite_version: 1,
  variants: ["hybrid", "dense_only"],
  status: "completed",
  case_count: 25,
  metrics: {
    hybrid_ndcg: 1,
    dense_only_ndcg: 0.75,
    citation_precision: 1,
    critical_safety_pass_rate: 1,
    p95_latency_ms: 120,
    failure_rate: 0,
  },
  gate_passed: true,
  gate_failures: [],
  created_at: "2026-07-29T00:00:00Z",
  completed_at: "2026-07-29T00:02:00Z",
  results: [
    {
      id: "result-1",
      case_id: "lookup-01",
      category: "lookup",
      variant: "hybrid",
      status: "passed",
      metrics: { ndcg: 1 },
      latency_ms: 42,
      model_calls: 1,
      prompt_tokens: 12,
      output_tokens: 0,
      failure_code: null,
      created_at: "2026-07-29T00:00:00Z",
    },
  ],
};

function successfulRequest(path: string, options?: RequestInit) {
  if (path.endsWith("/suite")) {
    return Promise.resolve({
      suite: "phase12-reviewed-v1",
      version: 1,
      reviewed_by: "DocPilot engineering",
      reviewed_at: "2026-07-29",
      case_count: 50,
      categories: { lookup: 10 },
      thresholds: { citation_precision: 0.95 },
    });
  }
  if (options?.method === "POST") return Promise.resolve(evaluation);
  if (path === "/v1/evaluations?limit=50") {
    return Promise.resolve({ items: [evaluation], next_cursor: null });
  }
  return Promise.resolve(evaluation);
}

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.requestJson.mockImplementation(successfulRequest);
});

test("launches a reviewed evaluation and displays release metrics", async () => {
  renderWithProviders(<EvaluationsPage />);

  expect(await screen.findByText(/50 reviewed cases/)).toBeInTheDocument();
  expect((await screen.findAllByText("phase12-reviewed-v1")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("100%")).length).toBeGreaterThan(0);
  expect(screen.getByText("lookup-01")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Run evaluation" }));
  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalledWith(
      "/v1/evaluations",
      expect.objectContaining({ method: "POST" }),
    );
  });
  fireEvent.click(screen.getByRole("button", { name: "Refresh evaluations" }));
  expect(mocks.requestJson).toHaveBeenCalled();
});

test("distinguishes unavailable, failed, and empty evaluation states", async () => {
  mocks.requestJson.mockImplementation((path: string) =>
    path.includes("?limit")
      ? Promise.reject(new ApiClientError("missing", 404))
      : successfulRequest(path),
  );
  const unavailable = renderWithProviders(<EvaluationsPage />);
  expect(await screen.findByText(/not enabled/)).toBeInTheDocument();
  unavailable.unmount();

  mocks.requestJson.mockImplementation((path: string) =>
    path.includes("?limit") ? Promise.reject(new Error("offline")) : successfulRequest(path),
  );
  const failed = renderWithProviders(<EvaluationsPage />);
  expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument();
  failed.unmount();

  mocks.requestJson.mockImplementation((path: string) =>
    path.includes("?limit")
      ? Promise.resolve({ items: [], next_cursor: null })
      : successfulRequest(path),
  );
  renderWithProviders(<EvaluationsPage />);
  expect(await screen.findByText(/No evaluation runs/)).toBeInTheDocument();
});
