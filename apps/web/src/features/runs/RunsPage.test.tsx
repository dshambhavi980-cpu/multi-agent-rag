import { fireEvent, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/render";
import { RunsPage } from "./RunsPage";

const mocks = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("../../api/client", () => ({ requestJson: mocks.requestJson }));
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

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.requestJson.mockImplementation((path: string) => {
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
