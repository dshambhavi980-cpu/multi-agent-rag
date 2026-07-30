import { fireEvent, screen, waitFor } from "@testing-library/react";

import { ApiClientError } from "../../api/client";
import { renderWithProviders } from "../../test/render";
import { RunsPage } from "./RunsPage";

const mocks = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("../../api/client", () => ({
  ApiClientError: class extends Error {
    constructor(
      message: string,
      readonly status: number,
    ) {
      super(message);
    }
  },
  requestJson: mocks.requestJson,
}));
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({ session: { access_token: "token" } }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "workspace-1" } }),
}));

const run = {
  id: "run-1",
  conversation_id: "conversation-1",
  question: "How is emergency access reset?",
  status: "completed",
  mode: "agentic",
  current_node: "complete",
  step_count: 2,
  confidence: 0.88,
  answer_status: "grounded",
  output_message_id: "message-1",
  approval_id: null,
  error: null,
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:01Z",
  completed_at: "2026-07-29T00:00:01Z",
};

const observability = {
  request_id: "request-1",
  trace_id: "trace-1",
  run_id: "run-1",
  model: "gemini-3.1-flash-lite",
  prompt_version: "rag-system-v2",
  timings: { total_ms: 42 },
  input_tokens: 12,
  output_tokens: 8,
  token_usage_source: "estimated",
  replayed_from_run_id: null,
  replay_mode: null,
  error: null,
  evidence: [],
  events: [
    {
      event_type: "run.status_changed",
      occurred_at: "2026-07-29T00:00:00.100Z",
      latency_ms: null,
      severity: "info",
      attributes: { status: "running" },
    },
    {
      event_type: "retrieval.completed",
      occurred_at: "2026-07-29T00:00:00.200Z",
      latency_ms: 12,
      severity: "info",
      attributes: { selected_chunks: 3 },
    },
    {
      event_type: "citations.available",
      occurred_at: "2026-07-29T00:00:00.300Z",
      latency_ms: null,
      severity: "info",
      attributes: {},
    },
    {
      event_type: "run.completed",
      occurred_at: "2026-07-29T00:00:00.400Z",
      latency_ms: null,
      severity: "info",
      attributes: { duration_ms: 42 },
    },
  ],
};

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.requestJson.mockImplementation((path: string) => {
    if (path.includes("/observability")) return Promise.resolve(observability);
    if (path.includes("/trace")) {
      return Promise.resolve({
        run,
        steps: [
          {
            id: "step-1",
            step_number: 1,
            node: "retrieve",
            status: "succeeded",
            summary: "Retrieved workspace evidence.",
            duration_ms: 12,
            created_at: "2026-07-29T00:00:00Z",
          },
        ],
        tool_calls: [
          {
            id: "tool-1",
            tool_name: "workspace_search",
            permission: "read",
            status: "succeeded",
            output_summary: { results: 3 },
            duration_ms: 8,
            created_at: "2026-07-29T00:00:00.500Z",
          },
        ],
      });
    }
    return Promise.resolve({ items: [run], next_cursor: null });
  });
});

test("shows a virtualized concise agent timeline", async () => {
  renderWithProviders(<RunsPage />);
  expect(await screen.findByText("How is emergency access reset?")).toBeInTheDocument();
  expect(await screen.findByText("Retrieved workspace evidence.")).toBeInTheDocument();
  expect(screen.getByText("workspace_search")).toBeInTheDocument();
  expect(screen.getByText(/decisions and tool outcomes only/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Refresh runs" }));
  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalled();
  });
});

test("renders empty and failed run states", async () => {
  mocks.requestJson.mockResolvedValueOnce({ items: [], next_cursor: null });
  const empty = renderWithProviders(<RunsPage />);
  expect(await screen.findByText(/No runs have been started/)).toBeInTheDocument();
  empty.unmount();

  mocks.requestJson.mockRejectedValueOnce(new Error("offline"));
  renderWithProviders(<RunsPage />);
  expect(await screen.findByText(/Run history could not be loaded/)).toBeInTheDocument();
});

test("shows operational stages for a fast RAG run", async () => {
  const fastRun = { ...run, mode: "simple", step_count: 0 };
  mocks.requestJson.mockImplementation((path: string) => {
    if (path.includes("/observability")) return Promise.resolve(observability);
    if (path.includes("/trace")) {
      return Promise.resolve({ run: fastRun, steps: [], tool_calls: [] });
    }
    return Promise.resolve({ items: [fastRun], next_cursor: null });
  });

  renderWithProviders(<RunsPage />);

  expect(await screen.findByText("Hybrid retrieval")).toBeInTheDocument();
  expect(screen.getByText("Selected 3 grounded evidence passages.")).toBeInTheDocument();
  expect(screen.getByText("Citation validation")).toBeInTheDocument();
  expect(screen.getByText("Run completed")).toBeInTheDocument();
  expect(screen.queryByText(/No agent trace/)).not.toBeInTheDocument();
});

test("shows the backend reason when an exact replay is unavailable", async () => {
  mocks.requestJson.mockImplementation((path: string, options?: RequestInit) => {
    if (options?.method === "POST") {
      return Promise.reject(
        new ApiClientError(
          "The stored model or prompt version is no longer available. Use current configuration.",
          409,
        ),
      );
    }
    if (path.includes("/observability")) return Promise.resolve(observability);
    if (path.includes("/trace")) {
      return Promise.resolve({ run, steps: [], tool_calls: [] });
    }
    return Promise.resolve({ items: [run], next_cursor: null });
  });

  renderWithProviders(<RunsPage />);
  await screen.findByText("Replay run");
  fireEvent.click(screen.getByRole("button", { name: "Exact" }));
  fireEvent.click(screen.getByRole("button", { name: "Start replay" }));

  expect(
    await screen.findByText(/stored model or prompt version is no longer available/i),
  ).toBeInTheDocument();
});
