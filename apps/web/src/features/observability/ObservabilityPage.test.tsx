import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/render";
import { ObservabilityPage } from "./ObservabilityPage";

const mocks = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("../../api/client", () => ({ requestJson: mocks.requestJson }));
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({ session: { access_token: "token" } }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "workspace-1" } }),
}));

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.requestJson.mockResolvedValue({
    window_hours: 24,
    total_runs: 10,
    successful_runs: 9,
    failed_runs: 1,
    success_rate: 0.9,
    p95_latency_ms: 824.4,
    input_tokens: 1200,
    output_tokens: 800,
    active_runs: 2,
    trace_count: 25,
    trace_limit: 50,
    retention_days: 30,
  });
});

test("shows health, latency, tokens, and bounded trace quota", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ObservabilityPage />);

  expect(await screen.findByText("90%")).toBeInTheDocument();
  expect(screen.getByText("824 ms")).toBeInTheDocument();
  expect(screen.getByText("2,000")).toBeInTheDocument();
  expect(screen.getByText("25 / 50")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Trace storage quota" })).toHaveValue(50);

  await user.click(screen.getByRole("button", { name: "Refresh operations" }));
  expect(mocks.requestJson).toHaveBeenCalledTimes(2);
});

test("shows an actionable metrics failure", async () => {
  mocks.requestJson.mockRejectedValue(new Error("offline"));
  renderWithProviders(<ObservabilityPage />);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Operational metrics could not be loaded",
  );
});
